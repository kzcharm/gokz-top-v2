from __future__ import annotations

import struct
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

from app.models import KZMode
from app.services.replay_parser_common import (
    MODE_BY_INDEX,
    REPLAY_FORMAT_VERSION,
    REPLAY_MAGIC,
    REPLAY_STYLE_NRM,
    REPLAY_TYPE_RUN,
    BinaryReader,
    ensure_finite,
    float_from_i32,
    steam_account_id_to_steamid64,
)

DECIMAL_THREE_PLACES = Decimal("0.001")


class RunReplayParseError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedRunReplay:
    source_name: str
    map_name: str
    recorded_at: datetime
    player_alias: str
    steamid64: int
    mode: KZMode
    course: int
    time: Decimal
    truncated_time: Decimal
    teleports_used: int
    map_file_size: int
    tick_count: int
    tickrate: float


def normalize_run_replay_time(value: float) -> Decimal:
    return Decimal(str(value)).quantize(
        DECIMAL_THREE_PLACES,
        rounding=ROUND_HALF_UP,
    )


def parse_run_replay_bytes(
    *, data: bytes, source_name: str, validate_ticks: bool = False
) -> ParsedRunReplay:
    try:
        reader = BinaryReader(data)

        magic = reader.read_u32()
        if magic != REPLAY_MAGIC:
            raise RunReplayParseError(f"{source_name}: invalid replay magic")

        version = reader.read_u8()
        if version != REPLAY_FORMAT_VERSION:
            raise RunReplayParseError(
                f"{source_name}: unsupported replay version {version}"
            )

        replay_type = reader.read_u8()
        if replay_type != REPLAY_TYPE_RUN:
            raise RunReplayParseError(f"{source_name}: replay is not a run replay")

        _gokz_version = reader.read_len_string_u8()
        map_name = reader.read_len_string_u8().strip()
        _map_file_size = reader.read_i32()
        _server_ip = reader.read_i32()
        timestamp = reader.read_i32()
        player_alias = reader.read_len_string_u8().strip()
        steam_account_id = reader.read_i32()
        mode_index = reader.read_u8()
        style_index = reader.read_u8()
        _player_sensitivity = float_from_i32(reader.read_i32())
        _player_myaw = float_from_i32(reader.read_i32())
        _tickrate = ensure_finite(
            value=float_from_i32(reader.read_i32()),
            label="tickrate",
            source_name=source_name,
            error_type=RunReplayParseError,
        )
        _tick_count = reader.read_i32()
        _weapon = reader.read_i32()
        _knife = reader.read_i32()

        time_seconds = ensure_finite(
            value=float_from_i32(reader.read_i32()),
            label="time",
            source_name=source_name,
            error_type=RunReplayParseError,
        )
        course = reader.read_u8()
        teleports_used = reader.read_i32()

        if not map_name:
            raise RunReplayParseError(
                f"{source_name}: replay map name must not be blank"
            )
        if style_index != REPLAY_STYLE_NRM:
            raise RunReplayParseError(
                f"{source_name}: unsupported replay style index {style_index}; expected NRM"
            )
        mode = MODE_BY_INDEX.get(mode_index)
        if mode is None:
            raise RunReplayParseError(
                f"{source_name}: unsupported replay mode index {mode_index}"
            )
        if course < 0:
            raise RunReplayParseError(
                f"{source_name}: replay course must be non-negative"
            )
        if teleports_used < 0:
            raise RunReplayParseError(
                f"{source_name}: replay teleports must be non-negative"
            )
        if time_seconds <= 0.0:
            raise RunReplayParseError(f"{source_name}: replay time must be positive")

        if validate_ticks:
            if _tickrate != 128.0 or _tick_count < 1 or _tick_count > len(data) // 4:
                raise RunReplayParseError(
                    f"{source_name}: invalid tick count or tickrate"
                )
            full_mask = (1 << 20) - 1
            for tick in range(_tick_count):
                flags = reader.read_u32()
                if (
                    not flags & 1
                    or flags & ~full_mask
                    or (tick == 0 and flags != full_mask)
                ):
                    raise RunReplayParseError(
                        f"{source_name}: invalid tick delta flags"
                    )
                for field in range(1, 20):
                    if flags & (1 << field):
                        value = reader.read_i32()
                        if field in {2, 3, 4, 7, 8, 9, 10, 11, 12, 13, 14, 15, 18}:
                            ensure_finite(
                                value=float_from_i32(value),
                                label="tick data",
                                source_name=source_name,
                                error_type=RunReplayParseError,
                            )
            if reader.remaining:
                raise RunReplayParseError(f"{source_name}: trailing replay data")
            if _tick_count < int(time_seconds * _tickrate) - 1:
                raise RunReplayParseError(
                    f"{source_name}: replay is shorter than the recorded run"
                )

        return ParsedRunReplay(
            map_file_size=_map_file_size,
            tick_count=_tick_count,
            tickrate=_tickrate,
            source_name=source_name,
            map_name=map_name,
            recorded_at=datetime.fromtimestamp(timestamp, UTC),
            player_alias=player_alias,
            steamid64=steam_account_id_to_steamid64(
                steam_account_id,
                error_type=RunReplayParseError,
            ),
            mode=mode,
            course=course,
            time=normalize_run_replay_time(time_seconds),
            truncated_time=Decimal(str(time_seconds)).quantize(
                DECIMAL_THREE_PLACES, rounding=ROUND_DOWN
            ),
            teleports_used=teleports_used,
        )
    except (struct.error, IndexError) as exc:
        raise RunReplayParseError(
            f"{source_name}: truncated or malformed replay"
        ) from exc
