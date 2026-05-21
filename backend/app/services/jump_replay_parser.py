from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from app.models import (
    JumpstatStrafeStat,
    JumpstatType,
    JumpstatVisualizationBounds,
    JumpstatVisualizationJumpDirection,
    JumpstatVisualizationMouseDirection,
    JumpstatVisualizationPublic,
    JumpstatVisualizationSample,
    JumpstatVisualizationStrafeType,
    KZMode,
)
from app.services.replay_parser_common import (
    MODE_BY_INDEX,
    REPLAY_FORMAT_VERSION,
    REPLAY_MAGIC,
    REPLAY_STYLE_NRM,
    REPLAY_TYPE_JUMP,
    BinaryReader,
    ensure_finite,
    float_from_i32,
    steam_account_id_to_steamid64,
)

GOKZ_DB_JS_AIRTIME_PRECISION = 10000

RP_IN_DUCK = 1 << 7
RP_IN_FORWARD = 1 << 8
RP_IN_BACK = 1 << 9
RP_IN_MOVELEFT = 1 << 12
RP_IN_MOVERIGHT = 1 << 13
RP_FL_ONGROUND = 1 << 18

EPSILON = 1e-6
MAX_STRAFES = 48
DECIMAL_FOUR_PLACES = Decimal("0.0001")
JUMPSTAT_VISUALIZATION_VERSION = 2
JUMPSTAT_TYPE_BY_INDEX: dict[int, JumpstatType] = {
    0: JumpstatType.LJ,
    1: JumpstatType.BH,
    2: JumpstatType.MBH,
    3: JumpstatType.WJ,
    4: JumpstatType.LAJ,
    5: JumpstatType.LAH,
    6: JumpstatType.JB,
    7: JumpstatType.LBH,
    8: JumpstatType.LWJ,
    9: JumpstatType.FL,
    10: JumpstatType.UNK,
    11: JumpstatType.INV,
}

LEFT_BUTTON_BY_JUMP_DIRECTION: dict[JumpstatVisualizationJumpDirection, int] = {
    JumpstatVisualizationJumpDirection.FORWARDS: RP_IN_MOVELEFT,
    JumpstatVisualizationJumpDirection.BACKWARDS: RP_IN_MOVERIGHT,
    JumpstatVisualizationJumpDirection.LEFT: RP_IN_BACK,
    JumpstatVisualizationJumpDirection.RIGHT: RP_IN_FORWARD,
}
RIGHT_BUTTON_BY_JUMP_DIRECTION: dict[JumpstatVisualizationJumpDirection, int] = {
    JumpstatVisualizationJumpDirection.FORWARDS: RP_IN_MOVERIGHT,
    JumpstatVisualizationJumpDirection.BACKWARDS: RP_IN_MOVELEFT,
    JumpstatVisualizationJumpDirection.LEFT: RP_IN_FORWARD,
    JumpstatVisualizationJumpDirection.RIGHT: RP_IN_BACK,
}


class JumpReplayParseError(ValueError):
    pass


@dataclass(frozen=True)
class Vec3:
    x: float
    y: float
    z: float


@dataclass(frozen=True)
class ReplayTick:
    forwardmove: float
    sidemove: float
    upmove: float
    mouse_x: int
    mouse_y: int
    origin: Vec3
    angles: Vec3
    velocity: Vec3
    flags: int
    on_ground: bool


@dataclass(frozen=True)
class JumpReplayHeader:
    source_name: str
    timestamp: int
    steam_account_id: int
    mode_index: int
    style_index: int
    jump_type_index: int
    distance: float
    block_distance: int
    strafe_count: int
    sync: float
    pre_speed: float
    max_speed: float
    airtime: int
    tickrate: float
    tick_count: int

    @property
    def airtime_ticks(self) -> int:
        return round((self.airtime / GOKZ_DB_JS_AIRTIME_PRECISION) * self.tickrate)


@dataclass(frozen=True)
class JumpSegment:
    start_air_tick: int
    end_air_tick: int
    landed: bool


@dataclass
class StrafeStats:
    ticks: int = 0
    gain_ticks: int = 0
    gain: float = 0.0
    loss: float = 0.0
    width: float = 0.0
    overlap: int = 0
    dead_air: int = 0

    @property
    def sync(self) -> float:
        if self.ticks == 0:
            return 0.0
        return (self.gain_ticks / self.ticks) * 100.0


@dataclass(frozen=True)
class DerivedJumpStats:
    duration: int
    strafes: int
    sync: float
    max_speed: float
    height: float
    offset: float
    deviation: float
    overlap: int
    dead_air: int
    crouch_ticks: int
    release_w: int
    total_width: float
    strafe_stats: list[StrafeStats]

    @property
    def average_width(self) -> float:
        if self.strafes == 0:
            return 0.0
        return self.total_width / self.strafes


@dataclass(frozen=True)
class ParsedJumpReplay:
    steamid64: int
    mode: KZMode
    type: JumpstatType
    distance: Decimal
    block: int | None
    strafes: int
    sync_percent: int
    pre_speed: Decimal
    max_speed: Decimal
    w_count: int
    overlap_count: int
    dead_air_count: int
    width: Decimal
    height: Decimal
    airtime_percent: int
    offset: Decimal
    deviation: Decimal
    crouched_ticks: int
    strafe_stats: list[dict[str, float | int]]
    jumped_at: datetime


@dataclass(frozen=True)
class SelectedJumpReplay:
    header: JumpReplayHeader
    steamid64: int
    mode: KZMode
    jump_type: JumpstatType
    ticks: list[ReplayTick]
    segment: JumpSegment
    stats: DerivedJumpStats


def wrap_angle_delta(current: float, previous: float) -> float:
    delta = current - previous
    while delta <= -180.0:
        delta += 360.0
    while delta > 180.0:
        delta -= 360.0
    return delta


def _normalize_angle(angle: float) -> float:
    while angle <= -180.0:
        angle += 360.0
    while angle > 180.0:
        angle -= 360.0
    return angle


def _to_decimal(value: float) -> Decimal:
    return Decimal(str(value)).quantize(DECIMAL_FOUR_PLACES, rounding=ROUND_HALF_UP)


def _to_percent(value: float) -> int:
    return max(0, min(100, int(round(value))))


def _parse_jump_replay_header(
    *,
    reader: BinaryReader,
    source_name: str,
) -> JumpReplayHeader:
    magic = reader.read_u32()
    if magic != REPLAY_MAGIC:
        raise JumpReplayParseError(f"{source_name}: invalid replay magic")

    version = reader.read_u8()
    if version != REPLAY_FORMAT_VERSION:
        raise JumpReplayParseError(
            f"{source_name}: unsupported replay version {version}"
        )

    replay_type = reader.read_u8()
    if replay_type != REPLAY_TYPE_JUMP:
        raise JumpReplayParseError(f"{source_name}: replay is not a jump replay")

    _gokz_version = reader.read_len_string_u8()
    _map_name = reader.read_len_string_u8()
    _map_file_size = reader.read_i32()
    _server_ip = reader.read_i32()
    timestamp = reader.read_i32()
    _alias = reader.read_len_string_u8()
    steam_account_id = reader.read_i32()
    mode_index = reader.read_u8()
    style_index = reader.read_u8()
    _player_sensitivity = float_from_i32(reader.read_i32())
    _player_myaw = float_from_i32(reader.read_i32())
    tickrate = float_from_i32(reader.read_i32())
    tick_count = reader.read_i32()
    _weapon = reader.read_i32()
    _knife = reader.read_i32()

    jump_type_index = reader.read_u8()
    distance = float_from_i32(reader.read_i32())
    block_distance = reader.read_i32()
    strafe_count = reader.read_u8()
    sync = float_from_i32(reader.read_i32())
    pre_speed = float_from_i32(reader.read_i32())
    max_speed = float_from_i32(reader.read_i32())
    airtime = reader.read_i32()

    tickrate = ensure_finite(
        value=tickrate,
        label="tickrate",
        source_name=source_name,
        error_type=JumpReplayParseError,
    )
    distance = ensure_finite(
        value=distance,
        label="distance",
        source_name=source_name,
        error_type=JumpReplayParseError,
    )
    sync = ensure_finite(
        value=sync,
        label="sync",
        source_name=source_name,
        error_type=JumpReplayParseError,
    )
    pre_speed = ensure_finite(
        value=pre_speed,
        label="pre speed",
        source_name=source_name,
        error_type=JumpReplayParseError,
    )
    max_speed = ensure_finite(
        value=max_speed,
        label="max speed",
        source_name=source_name,
        error_type=JumpReplayParseError,
    )

    return JumpReplayHeader(
        source_name=source_name,
        timestamp=timestamp,
        steam_account_id=steam_account_id,
        mode_index=mode_index,
        style_index=style_index,
        jump_type_index=jump_type_index,
        distance=distance,
        block_distance=block_distance,
        strafe_count=strafe_count,
        sync=sync,
        pre_speed=pre_speed,
        max_speed=max_speed,
        airtime=airtime,
        tickrate=tickrate,
        tick_count=tick_count,
    )


def _parse_ticks(*, reader: BinaryReader, header: JumpReplayHeader) -> list[ReplayTick]:
    tick_array = [0] * 20
    ticks: list[ReplayTick] = []

    for index in range(header.tick_count):
        tick_array[0] = reader.read_i32()
        delta_flags = tick_array[0]
        for field_index in range(1, 20):
            if delta_flags & (1 << field_index):
                tick_array[field_index] = reader.read_i32()

        origin = Vec3(
            ensure_finite(
                value=float_from_i32(tick_array[7]),
                label="origin.x",
                source_name=header.source_name,
                error_type=JumpReplayParseError,
            ),
            ensure_finite(
                value=float_from_i32(tick_array[8]),
                label="origin.y",
                source_name=header.source_name,
                error_type=JumpReplayParseError,
            ),
            ensure_finite(
                value=float_from_i32(tick_array[9]),
                label="origin.z",
                source_name=header.source_name,
                error_type=JumpReplayParseError,
            ),
        )
        angles = Vec3(
            ensure_finite(
                value=float_from_i32(tick_array[10]),
                label="angles.x",
                source_name=header.source_name,
                error_type=JumpReplayParseError,
            ),
            ensure_finite(
                value=float_from_i32(tick_array[11]),
                label="angles.y",
                source_name=header.source_name,
                error_type=JumpReplayParseError,
            ),
            ensure_finite(
                value=float_from_i32(tick_array[12]),
                label="angles.z",
                source_name=header.source_name,
                error_type=JumpReplayParseError,
            ),
        )
        velocity = Vec3(
            ensure_finite(
                value=float_from_i32(tick_array[13]),
                label="velocity.x",
                source_name=header.source_name,
                error_type=JumpReplayParseError,
            ),
            ensure_finite(
                value=float_from_i32(tick_array[14]),
                label="velocity.y",
                source_name=header.source_name,
                error_type=JumpReplayParseError,
            ),
            ensure_finite(
                value=float_from_i32(tick_array[15]),
                label="velocity.z",
                source_name=header.source_name,
                error_type=JumpReplayParseError,
            ),
        )
        flags = tick_array[16]

        if (
            index > 0
            and origin.x == 0.0
            and origin.y == 0.0
            and origin.z == 0.0
            and angles.x == 0.0
            and angles.y == 0.0
        ):
            break

        ticks.append(
            ReplayTick(
                forwardmove=float_from_i32(tick_array[2]),
                sidemove=float_from_i32(tick_array[3]),
                upmove=float_from_i32(tick_array[4]),
                mouse_x=tick_array[5],
                mouse_y=tick_array[6],
                origin=origin,
                angles=angles,
                velocity=velocity,
                flags=flags,
                on_ground=bool(flags & RP_FL_ONGROUND),
            )
        )

    if not ticks:
        raise JumpReplayParseError(
            f"{header.source_name}: replay does not contain ticks"
        )
    return ticks


def _find_air_segments(ticks: list[ReplayTick]) -> list[JumpSegment]:
    segments: list[JumpSegment] = []
    previous_on_ground = True
    start_air_tick: int | None = None

    for index, tick in enumerate(ticks):
        if not tick.on_ground and previous_on_ground:
            start_air_tick = index
        elif tick.on_ground and not previous_on_ground and start_air_tick is not None:
            segments.append(
                JumpSegment(
                    start_air_tick=start_air_tick,
                    end_air_tick=index - 1,
                    landed=True,
                )
            )
            start_air_tick = None
        previous_on_ground = tick.on_ground

    if start_air_tick is not None:
        segments.append(
            JumpSegment(
                start_air_tick=start_air_tick,
                end_air_tick=len(ticks) - 1,
                landed=False,
            )
        )

    return segments


def _stable_landing_z(ticks: list[ReplayTick], end_air_tick: int) -> float:
    post_ground_z = [
        ticks[index].origin.z
        for index in range(end_air_tick + 1, min(len(ticks), end_air_tick + 10))
        if ticks[index].on_ground
    ]
    if not post_ground_z:
        return ticks[end_air_tick].origin.z
    return min(post_ground_z)


def _get_coord_orientation(
    start_x: float,
    start_y: float,
    end_x: float,
    end_y: float,
) -> tuple[int, int]:
    coord_dist = int(abs(end_x - start_x) < abs(end_y - start_y))
    coord_dev = 1 - coord_dist
    return coord_dist, coord_dev


def _derive_segment_stats(
    *,
    ticks: list[ReplayTick],
    segment: JumpSegment,
) -> DerivedJumpStats:
    start_air_tick = segment.start_air_tick
    base_tick = max(0, start_air_tick - 1)
    landing_tick = (
        segment.end_air_tick + 1
        if segment.landed and segment.end_air_tick + 1 < len(ticks)
        else segment.end_air_tick
    )

    takeoff_z = ticks[base_tick].origin.z
    landing_z = (
        _stable_landing_z(ticks, segment.end_air_tick)
        if segment.landed
        else ticks[landing_tick].origin.z
    )
    takeoff_x = ticks[base_tick].origin.x
    takeoff_y = ticks[base_tick].origin.y
    landing_x = ticks[landing_tick].origin.x
    landing_y = ticks[landing_tick].origin.y
    _coord_dist, coord_dev = _get_coord_orientation(
        takeoff_x, takeoff_y, landing_x, landing_y
    )
    deviation = abs(
        (landing_x - takeoff_x) if coord_dev == 0 else (landing_y - takeoff_y)
    )

    previous_speed = math.hypot(
        ticks[base_tick].velocity.x, ticks[base_tick].velocity.y
    )
    previous_yaw = ticks[base_tick].angles.y

    duration = 0
    sync_ticks = 0
    max_speed = 0.0
    height = 0.0
    overlap = 0
    dead_air = 0
    crouch_ticks = 0
    total_width = 0.0
    strafes = 0
    strafe_direction = 0
    release_w = 100
    last_forward_tick = base_tick
    strafe_stats = [StrafeStats() for _ in range(MAX_STRAFES)]

    for index in range(base_tick + 1, landing_tick + 1):
        tick = ticks[index]
        current_speed = math.hypot(tick.velocity.x, tick.velocity.y)
        yaw_delta = wrap_angle_delta(tick.angles.y, previous_yaw)

        if yaw_delta < -EPSILON and strafe_direction != -1:
            strafe_direction = -1
            strafes += 1
        elif yaw_delta > EPSILON and strafe_direction != 1:
            strafe_direction = 1
            strafes += 1

        current_strafe = min(strafes, MAX_STRAFES - 1)
        overlap_tick = int(
            bool(tick.flags & RP_IN_MOVELEFT) and bool(tick.flags & RP_IN_MOVERIGHT)
        )
        dead_air_tick = int(
            not (tick.flags & RP_IN_MOVELEFT) and not (tick.flags & RP_IN_MOVERIGHT)
        )
        delta_speed = current_speed - previous_speed
        width = abs(yaw_delta)

        current_stats = strafe_stats[current_strafe]
        current_stats.ticks += 1
        current_stats.overlap += overlap_tick
        current_stats.dead_air += dead_air_tick
        current_stats.width += width

        if delta_speed > EPSILON:
            current_stats.gain_ticks += 1
            current_stats.gain += delta_speed
            sync_ticks += 1
        elif delta_speed < -EPSILON:
            current_stats.loss += -delta_speed

        if tick.flags & (RP_IN_FORWARD | RP_IN_BACK):
            last_forward_tick = index
        elif release_w > 99:
            release_w = last_forward_tick - start_air_tick + 1

        overlap += overlap_tick
        dead_air += dead_air_tick
        total_width += width
        height = max(height, tick.origin.z - takeoff_z)
        max_speed = max(max_speed, current_speed)
        crouch_ticks += int(bool(tick.flags & RP_IN_DUCK))
        duration += 1

        previous_speed = current_speed
        previous_yaw = tick.angles.y

    return DerivedJumpStats(
        duration=duration,
        strafes=strafes,
        sync=(sync_ticks / duration) * 100.0 if duration else 0.0,
        max_speed=max_speed,
        height=height,
        offset=landing_z - takeoff_z,
        deviation=deviation,
        overlap=overlap,
        dead_air=dead_air,
        crouch_ticks=crouch_ticks,
        release_w=release_w,
        total_width=total_width,
        strafe_stats=strafe_stats,
    )


def _segment_match_score(header: JumpReplayHeader, stats: DerivedJumpStats) -> float:
    return (
        abs(stats.duration - header.airtime_ticks) * 5.0
        + abs(stats.strafes - header.strafe_count) * 3.0
        + abs(stats.sync - header.sync) / 5.0
        + abs(stats.max_speed - header.max_speed) / 20.0
    )


def _choose_best_segment(
    *,
    header: JumpReplayHeader,
    ticks: list[ReplayTick],
) -> tuple[JumpSegment, DerivedJumpStats]:
    segments = _find_air_segments(ticks)
    if not segments:
        raise JumpReplayParseError(f"{header.source_name}: no airborne segment found")

    scored_segments = [
        (segment, _derive_segment_stats(ticks=ticks, segment=segment))
        for segment in segments
    ]
    return min(scored_segments, key=lambda item: _segment_match_score(header, item[1]))


def _parse_selected_jump_replay(
    *,
    data: bytes,
    source_name: str,
) -> SelectedJumpReplay:
    try:
        reader = BinaryReader(data)
        header = _parse_jump_replay_header(reader=reader, source_name=source_name)

        if header.style_index != REPLAY_STYLE_NRM:
            raise JumpReplayParseError(
                f"{source_name}: unsupported replay style index {header.style_index}"
            )

        mode = MODE_BY_INDEX.get(header.mode_index)
        if mode is None:
            raise JumpReplayParseError(
                f"{source_name}: unsupported replay mode index {header.mode_index}"
            )

        jump_type = JUMPSTAT_TYPE_BY_INDEX.get(header.jump_type_index)
        if jump_type is None:
            raise JumpReplayParseError(
                f"{source_name}: unsupported jump type index {header.jump_type_index}"
            )

        ticks = _parse_ticks(reader=reader, header=header)
        segment, stats = _choose_best_segment(header=header, ticks=ticks)
        if stats.strafes < 1:
            raise JumpReplayParseError(
                f"{source_name}: replay produced no valid strafes"
            )

        return SelectedJumpReplay(
            header=header,
            steamid64=steam_account_id_to_steamid64(
                header.steam_account_id,
                error_type=JumpReplayParseError,
            ),
            mode=mode,
            jump_type=jump_type,
            ticks=ticks,
            segment=segment,
            stats=stats,
        )
    except struct.error as exc:
        raise JumpReplayParseError(
            f"{source_name}: truncated or malformed replay"
        ) from exc


def _derive_jump_direction(
    *,
    ticks: list[ReplayTick],
    base_tick: int,
    jump_type: JumpstatType,
) -> JumpstatVisualizationJumpDirection:
    speed = math.hypot(ticks[base_tick].velocity.x, ticks[base_tick].velocity.y)
    if speed <= 50.0 or jump_type == JumpstatType.LAJ:
        return JumpstatVisualizationJumpDirection.FORWARDS

    velocity_direction = math.degrees(
        math.atan2(ticks[base_tick].velocity.y, ticks[base_tick].velocity.x)
    )
    direction = wrap_angle_delta(ticks[base_tick].angles.y, velocity_direction)

    if 45.0 <= direction <= 135.0:
        return JumpstatVisualizationJumpDirection.RIGHT
    if -135.0 <= direction <= -45.0:
        return JumpstatVisualizationJumpDirection.LEFT
    if direction > 135.0 or direction < -135.0:
        return JumpstatVisualizationJumpDirection.BACKWARDS
    return JumpstatVisualizationJumpDirection.FORWARDS


def _is_wishspeed_moving_left(
    *,
    forwardmove: float,
    sidemove: float,
    jump_direction: JumpstatVisualizationJumpDirection,
) -> bool:
    if jump_direction == JumpstatVisualizationJumpDirection.FORWARDS:
        return sidemove < 0.0
    if jump_direction == JumpstatVisualizationJumpDirection.BACKWARDS:
        return sidemove > 0.0
    if jump_direction == JumpstatVisualizationJumpDirection.LEFT:
        return forwardmove < 0.0
    return forwardmove > 0.0


def _is_wishspeed_moving_right(
    *,
    forwardmove: float,
    sidemove: float,
    jump_direction: JumpstatVisualizationJumpDirection,
) -> bool:
    if jump_direction == JumpstatVisualizationJumpDirection.FORWARDS:
        return sidemove > 0.0
    if jump_direction == JumpstatVisualizationJumpDirection.BACKWARDS:
        return sidemove < 0.0
    if jump_direction == JumpstatVisualizationJumpDirection.LEFT:
        return forwardmove > 0.0
    return forwardmove < 0.0


def _classify_strafe_type(
    *,
    tick: ReplayTick,
    jump_direction: JumpstatVisualizationJumpDirection,
) -> JumpstatVisualizationStrafeType:
    left_button = LEFT_BUTTON_BY_JUMP_DIRECTION[jump_direction]
    right_button = RIGHT_BUTTON_BY_JUMP_DIRECTION[jump_direction]
    move_left = bool(tick.flags & left_button)
    move_right = bool(tick.flags & right_button)
    vel_left = _is_wishspeed_moving_left(
        forwardmove=tick.forwardmove,
        sidemove=tick.sidemove,
        jump_direction=jump_direction,
    )
    vel_right = _is_wishspeed_moving_right(
        forwardmove=tick.forwardmove,
        sidemove=tick.sidemove,
        jump_direction=jump_direction,
    )
    vel_is_zero = not vel_left and not vel_right

    if move_left and not move_right:
        if vel_left:
            return JumpstatVisualizationStrafeType.LEFT
        if vel_right:
            return JumpstatVisualizationStrafeType.RIGHT
    elif move_right and not move_left:
        if vel_right:
            return JumpstatVisualizationStrafeType.RIGHT
        if vel_left:
            return JumpstatVisualizationStrafeType.LEFT
    elif move_left and move_right:
        if vel_is_zero:
            return JumpstatVisualizationStrafeType.OVERLAP
        if vel_left:
            return JumpstatVisualizationStrafeType.OVERLAP_LEFT
        if vel_right:
            return JumpstatVisualizationStrafeType.OVERLAP_RIGHT
    else:
        if vel_is_zero:
            return JumpstatVisualizationStrafeType.NONE
        if vel_left:
            return JumpstatVisualizationStrafeType.NONE_LEFT
        if vel_right:
            return JumpstatVisualizationStrafeType.NONE_RIGHT

    return JumpstatVisualizationStrafeType.NONE


def _mouse_direction_from_yaw_delta(
    yaw_delta: float,
) -> JumpstatVisualizationMouseDirection:
    if yaw_delta < -EPSILON:
        return JumpstatVisualizationMouseDirection.LEFT
    if yaw_delta > EPSILON:
        return JumpstatVisualizationMouseDirection.RIGHT
    return JumpstatVisualizationMouseDirection.NONE


def _canonicalize_route_offset(*, x: float, y: float, delta_x: float, delta_y: float) -> tuple[float, float]:
    if abs(delta_x) >= abs(delta_y):
        if delta_x >= 0.0:
            return (-y, x)
        return (y, -x)

    if delta_y >= 0.0:
        return (x, y)
    return (-x, -y)


def parse_jump_replay_bytes(
    *,
    data: bytes,
    source_name: str,
) -> ParsedJumpReplay:
    selected = _parse_selected_jump_replay(data=data, source_name=source_name)
    stats = selected.stats
    duration = max(1, stats.duration)
    strafe_stats = [
        JumpstatStrafeStat(
            index=index,
            sync_percent=_to_percent(current.sync),
            gain=float(_to_decimal(current.gain)),
            loss=float(_to_decimal(current.loss)),
            airtime_percent=_to_percent((current.ticks / duration) * 100.0),
            width=float(_to_decimal(current.width)),
            overlap_count=current.overlap,
            dead_air_count=current.dead_air,
        ).model_dump(mode="json")
        for index, current in enumerate(
            stats.strafe_stats[1 : stats.strafes + 1], start=1
        )
    ]

    return ParsedJumpReplay(
        steamid64=selected.steamid64,
        mode=selected.mode,
        type=selected.jump_type,
        distance=_to_decimal(selected.header.distance),
        block=selected.header.block_distance if selected.header.block_distance > 0 else None,
        strafes=stats.strafes,
        sync_percent=_to_percent(stats.sync),
        pre_speed=_to_decimal(selected.header.pre_speed),
        max_speed=_to_decimal(stats.max_speed),
        w_count=max(0, stats.release_w),
        overlap_count=stats.overlap,
        dead_air_count=stats.dead_air,
        width=_to_decimal(stats.average_width),
        height=_to_decimal(stats.height),
        airtime_percent=100,
        offset=_to_decimal(stats.offset),
        deviation=_to_decimal(stats.deviation),
        crouched_ticks=stats.crouch_ticks,
        strafe_stats=strafe_stats,
        jumped_at=datetime.fromtimestamp(selected.header.timestamp, UTC),
    )


def parse_jump_replay_visualization(
    *,
    data: bytes,
    source_name: str,
) -> JumpstatVisualizationPublic:
    selected = _parse_selected_jump_replay(data=data, source_name=source_name)
    ticks = selected.ticks
    segment = selected.segment
    base_tick = max(0, segment.start_air_tick - 1)
    landing_tick = (
        segment.end_air_tick + 1
        if segment.landed and segment.end_air_tick + 1 < len(ticks)
        else segment.end_air_tick
    )
    takeoff_x = ticks[base_tick].origin.x
    takeoff_y = ticks[base_tick].origin.y
    landing_x = ticks[landing_tick].origin.x
    landing_y = ticks[landing_tick].origin.y
    delta_x = landing_x - takeoff_x
    delta_y = landing_y - takeoff_y
    jump_direction = _derive_jump_direction(
        ticks=ticks,
        base_tick=base_tick,
        jump_type=selected.jump_type,
    )
    left_button = LEFT_BUTTON_BY_JUMP_DIRECTION[jump_direction]
    right_button = RIGHT_BUTTON_BY_JUMP_DIRECTION[jump_direction]

    samples: list[JumpstatVisualizationSample] = []
    previous_yaw = ticks[base_tick].angles.y
    for relative_index, tick_index in enumerate(
        range(segment.start_air_tick, landing_tick + 1)
    ):
        tick = ticks[tick_index]
        canonical_x, canonical_y = _canonicalize_route_offset(
            x=tick.origin.x - takeoff_x,
            y=tick.origin.y - takeoff_y,
            delta_x=delta_x,
            delta_y=delta_y,
        )
        samples.append(
            JumpstatVisualizationSample(
                index=relative_index,
                x=float(_to_decimal(canonical_x)),
                y=float(_to_decimal(canonical_y)),
                yaw_delta=0.0,
                mouse_direction=JumpstatVisualizationMouseDirection.NONE,
                a_pressed=bool(tick.flags & left_button),
                d_pressed=bool(tick.flags & right_button),
                strafe_type=_classify_strafe_type(
                    tick=tick,
                    jump_direction=jump_direction,
                ),
            )
        )

        yaw_delta = wrap_angle_delta(tick.angles.y, previous_yaw)
        mouse_index = max(relative_index - 1, 0)
        samples[mouse_index].yaw_delta = float(_to_decimal(yaw_delta))
        samples[mouse_index].mouse_direction = _mouse_direction_from_yaw_delta(yaw_delta)
        previous_yaw = tick.angles.y

    if samples:
        end_sample = samples[-1]
        deviation_angle = _to_decimal(
            abs(math.degrees(math.atan2(end_sample.x, max(end_sample.y, EPSILON))))
        )
    else:
        deviation_angle = _to_decimal(0.0)

    if samples:
        bounds = JumpstatVisualizationBounds(
            min_x=min(sample.x for sample in samples),
            max_x=max(sample.x for sample in samples),
            min_y=min(sample.y for sample in samples),
            max_y=max(sample.y for sample in samples),
        )
    else:
        bounds = JumpstatVisualizationBounds(
            min_x=0.0,
            max_x=0.0,
            min_y=0.0,
            max_y=0.0,
        )

    return JumpstatVisualizationPublic(
        version=JUMPSTAT_VISUALIZATION_VERSION,
        jump_direction=jump_direction,
        deviation_angle=float(deviation_angle),
        bounds=bounds,
        samples=samples,
    )
