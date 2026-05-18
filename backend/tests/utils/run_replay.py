from __future__ import annotations

import struct
from dataclasses import dataclass
from datetime import UTC, datetime

from app.services.run_replay_parser import normalize_run_replay_time


@dataclass(frozen=True)
class SyntheticRunReplay:
    replay_bytes: bytes
    steamid64: int
    recorded_at: datetime
    map_name: str


def _pack_len_string(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return struct.pack("<B", len(encoded)) + encoded


def _pack_float_as_i32(value: float) -> bytes:
    return struct.pack("<i", struct.unpack("<i", struct.pack("<f", value))[0])


def build_synthetic_run_replay(
    *,
    magic: int = 0x676F6B7A,
    version: int = 2,
    replay_type: int = 0,
    map_name: str = "kz_test_run",
    timestamp: int = 1715860800,
    player_alias: str = "Run Runner",
    steam_account_id: int = 12345,
    mode_index: int = 2,
    style_index: int = 0,
    tickrate: float = 128.0,
    tick_count: int = 0,
    time_seconds: float = 35.289,
    course: int = 0,
    teleports_used: int = 0,
) -> SyntheticRunReplay:
    header = bytearray()
    header.extend(struct.pack("<I", magic))
    header.extend(struct.pack("<B", version))
    header.extend(struct.pack("<B", replay_type))
    header.extend(_pack_len_string("1.0.0"))
    header.extend(_pack_len_string(map_name))
    header.extend(struct.pack("<i", 123))
    header.extend(struct.pack("<i", 0))
    header.extend(struct.pack("<i", timestamp))
    header.extend(_pack_len_string(player_alias))
    header.extend(struct.pack("<i", steam_account_id))
    header.extend(struct.pack("<B", mode_index))
    header.extend(struct.pack("<B", style_index))
    header.extend(_pack_float_as_i32(1.5))
    header.extend(_pack_float_as_i32(0.022))
    header.extend(_pack_float_as_i32(tickrate))
    header.extend(struct.pack("<i", tick_count))
    header.extend(struct.pack("<i", 0))
    header.extend(struct.pack("<i", 0))
    header.extend(_pack_float_as_i32(time_seconds))
    header.extend(struct.pack("<i", course))
    header.extend(struct.pack("<i", teleports_used))

    return SyntheticRunReplay(
        replay_bytes=bytes(header),
        steamid64=76561197960265728 + steam_account_id,
        recorded_at=datetime.fromtimestamp(timestamp, UTC),
        map_name=map_name,
    )


def expected_time(value: float = 35.289) -> str:
    return str(normalize_run_replay_time(value))
