from __future__ import annotations

import struct
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

RP_IN_DUCK = 1 << 7
RP_IN_FORWARD = 1 << 8
RP_IN_MOVELEFT = 1 << 12
RP_IN_MOVERIGHT = 1 << 13
RP_FL_ONGROUND = 1 << 18


@dataclass(frozen=True)
class SyntheticJumpReplay:
    replay_bytes: bytes
    steamid64: int
    jumped_at: datetime


@dataclass(frozen=True)
class SyntheticReplayTick:
    origin: tuple[float, float, float]
    angles: tuple[float, float, float]
    velocity: tuple[float, float, float]
    flags: int
    forwardmove: float = 0.0
    sidemove: float = 0.0
    upmove: float = 0.0
    mouse: tuple[int, int] = (0, 0)


def _pack_len_string(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return struct.pack("<B", len(encoded)) + encoded


def _pack_float_as_i32(value: float) -> bytes:
    return struct.pack("<i", struct.unpack("<i", struct.pack("<f", value))[0])


def _tick_bytes(
    *,
    origin: tuple[float, float, float],
    angles: tuple[float, float, float],
    velocity: tuple[float, float, float],
    flags: int,
    forwardmove: float = 0.0,
    sidemove: float = 0.0,
    upmove: float = 0.0,
    mouse: tuple[int, int] = (0, 0),
) -> bytes:
    fields = {
        2: _pack_float_as_i32(forwardmove),
        3: _pack_float_as_i32(sidemove),
        4: _pack_float_as_i32(upmove),
        5: struct.pack("<i", mouse[0]),
        6: struct.pack("<i", mouse[1]),
        7: _pack_float_as_i32(origin[0]),
        8: _pack_float_as_i32(origin[1]),
        9: _pack_float_as_i32(origin[2]),
        10: _pack_float_as_i32(angles[0]),
        11: _pack_float_as_i32(angles[1]),
        12: _pack_float_as_i32(angles[2]),
        13: _pack_float_as_i32(velocity[0]),
        14: _pack_float_as_i32(velocity[1]),
        15: _pack_float_as_i32(velocity[2]),
        16: struct.pack("<i", flags),
    }
    delta_flags = 0
    payload = bytearray()
    for index in sorted(fields):
        delta_flags |= 1 << index
        payload.extend(fields[index])
    return struct.pack("<i", delta_flags) + payload


def build_synthetic_jump_replay(
    *,
    magic: int = 0x676F6B7A,
    version: int = 2,
    replay_type: int = 2,
    mode_index: int = 2,
    style_index: int = 0,
    jump_type_index: int = 0,
    block_distance: int = 260,
    ticks: list[SyntheticReplayTick] | None = None,
) -> SyntheticJumpReplay:
    timestamp = 1715860800
    steam_account_id = 12345
    steamid64 = 76561197960265728 + steam_account_id

    tick_specs = ticks or [
        SyntheticReplayTick(
            origin=(0.0, 0.0, 0.0),
            angles=(0.0, 10.0, 0.0),
            velocity=(100.0, 0.0, 0.0),
            flags=RP_FL_ONGROUND | RP_IN_FORWARD,
            forwardmove=450.0,
        ),
        SyntheticReplayTick(
            origin=(1.0, 0.0, 1.0),
            angles=(0.0, 20.0, 0.0),
            velocity=(150.0, 0.0, 10.0),
            flags=RP_IN_FORWARD,
            forwardmove=450.0,
            sidemove=450.0,
            mouse=(10, 0),
        ),
        SyntheticReplayTick(
            origin=(3.0, 1.0, 2.0),
            angles=(0.0, 15.0, 0.0),
            velocity=(130.0, 20.0, 5.0),
            flags=RP_IN_MOVELEFT,
            forwardmove=450.0,
            sidemove=-450.0,
            mouse=(-14, 0),
        ),
        SyntheticReplayTick(
            origin=(6.0, 1.0, 1.0),
            angles=(0.0, 25.0, 0.0),
            velocity=(200.0, 0.0, -5.0),
            flags=RP_IN_MOVERIGHT | RP_IN_DUCK,
            forwardmove=450.0,
            sidemove=450.0,
            mouse=(20, 0),
        ),
        SyntheticReplayTick(
            origin=(10.0, 2.0, 0.0),
            angles=(0.0, 35.0, 0.0),
            velocity=(180.0, 0.0, -20.0),
            flags=RP_FL_ONGROUND | RP_IN_DUCK,
            forwardmove=450.0,
            sidemove=450.0,
            mouse=(24, 0),
        ),
    ]
    tick_bytes = [
        _tick_bytes(
            origin=tick.origin,
            angles=tick.angles,
            velocity=tick.velocity,
            flags=tick.flags,
            forwardmove=tick.forwardmove,
            sidemove=tick.sidemove,
            upmove=tick.upmove,
            mouse=tick.mouse,
        )
        for tick in tick_specs
    ]

    header = bytearray()
    header.extend(struct.pack("<I", magic))
    header.extend(struct.pack("<B", version))
    header.extend(struct.pack("<B", replay_type))
    header.extend(_pack_len_string("1.0.0"))
    header.extend(_pack_len_string("kz_test_jump"))
    header.extend(struct.pack("<i", 123))
    header.extend(struct.pack("<i", 0))
    header.extend(struct.pack("<i", timestamp))
    header.extend(_pack_len_string("Jump Runner"))
    header.extend(struct.pack("<i", steam_account_id))
    header.extend(struct.pack("<B", mode_index))
    header.extend(struct.pack("<B", style_index))
    header.extend(_pack_float_as_i32(1.5))
    header.extend(_pack_float_as_i32(0.022))
    header.extend(_pack_float_as_i32(128.0))
    header.extend(struct.pack("<i", len(tick_bytes)))
    header.extend(struct.pack("<i", 0))
    header.extend(struct.pack("<i", 0))
    header.extend(struct.pack("<B", jump_type_index))
    header.extend(_pack_float_as_i32(281.8030))
    header.extend(struct.pack("<i", block_distance))
    header.extend(struct.pack("<B", 3))
    header.extend(_pack_float_as_i32(50.0))
    header.extend(_pack_float_as_i32(276.1))
    header.extend(_pack_float_as_i32(200.0))
    header.extend(struct.pack("<i", 313))

    replay_bytes = bytes(header) + b"".join(tick_bytes)
    return SyntheticJumpReplay(
        replay_bytes=replay_bytes,
        steamid64=steamid64,
        jumped_at=datetime.fromtimestamp(timestamp, UTC),
    )


def expected_parent_values() -> dict[str, object]:
    return {
        "distance": Decimal("281.8030"),
        "block": 260,
        "strafes": 3,
        "sync_percent": 50,
        "pre_speed": Decimal("276.1000"),
        "max_speed": Decimal("200.0000"),
        "w_count": 1,
        "overlap_count": 0,
        "dead_air_count": 2,
        "width": Decimal("11.6667"),
        "height": Decimal("2.0000"),
        "airtime_percent": 100,
        "offset": Decimal("0.0000"),
        "deviation": Decimal("2.0000"),
        "crouched_ticks": 2,
    }


def expected_strafe_stats() -> list[dict[str, float | int]]:
    return [
        {
            "index": 1,
            "sync_percent": 100,
            "gain": 50.0,
            "loss": 0.0,
            "airtime_percent": 25,
            "width": 10.0,
            "overlap_count": 0,
            "dead_air_count": 1,
        },
        {
            "index": 2,
            "sync_percent": 0,
            "gain": 0.0,
            "loss": 18.4705,
            "airtime_percent": 25,
            "width": 5.0,
            "overlap_count": 0,
            "dead_air_count": 0,
        },
        {
            "index": 3,
            "sync_percent": 50,
            "gain": 68.4705,
            "loss": 20.0,
            "airtime_percent": 50,
            "width": 20.0,
            "overlap_count": 0,
            "dead_air_count": 1,
        },
    ]
