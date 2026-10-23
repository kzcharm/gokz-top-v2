from decimal import Decimal

import pytest

from app.models import KZMode
from app.services.run_replay_parser import (
    RunReplayParseError,
    parse_run_replay_bytes,
)
from tests.utils.run_replay import build_synthetic_run_replay


def test_parse_run_replay_bytes_returns_expected_values() -> None:
    synthetic = build_synthetic_run_replay(
        map_name="kz_parser_map",
        time_seconds=35.289,
        course=2,
        teleports_used=3,
    )

    parsed = parse_run_replay_bytes(
        data=synthetic.replay_bytes,
        source_name="synthetic.replay",
    )

    assert parsed.map_name == "kz_parser_map"
    assert parsed.recorded_at == synthetic.recorded_at
    assert parsed.player_alias == "Run Runner"
    assert parsed.steamid64 == synthetic.steamid64
    assert parsed.mode == KZMode.KZT
    assert parsed.course == 2
    assert parsed.time == Decimal("35.289")
    assert parsed.teleports_used == 3


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"magic": 0xDEADBEEF}, "invalid replay magic"),
        ({"version": 1}, "unsupported replay version"),
        ({"replay_type": 2}, "not a run replay"),
        ({"style_index": 1}, "expected NRM"),
        ({"mode_index": 9}, "unsupported replay mode"),
    ],
)
def test_parse_run_replay_bytes_rejects_invalid_headers(
    kwargs: dict[str, int],
    message: str,
) -> None:
    synthetic = build_synthetic_run_replay(**kwargs)

    with pytest.raises(RunReplayParseError, match=message):
        parse_run_replay_bytes(
            data=synthetic.replay_bytes,
            source_name="invalid.replay",
        )


def test_parse_run_replay_bytes_rejects_blank_map_name() -> None:
    synthetic = build_synthetic_run_replay(map_name="   ")

    with pytest.raises(RunReplayParseError, match="map name must not be blank"):
        parse_run_replay_bytes(
            data=synthetic.replay_bytes,
            source_name="blank-map.replay",
        )


def test_parse_run_replay_bytes_rejects_truncated_replay() -> None:
    with pytest.raises(RunReplayParseError, match="truncated or malformed replay"):
        parse_run_replay_bytes(data=b"", source_name="empty.replay")


@pytest.mark.parametrize(
    "index,mode",
    [(0, KZMode.VNL), (1, KZMode.SKZ), (2, KZMode.KZT), (3, KZMode.NKZ)],
)
def test_gokz_mode_and_byte_course_layout(index: int, mode: KZMode) -> None:
    replay = build_synthetic_run_replay(
        mode_index=index, course=255, teleports_used=0x01020304
    )
    # Both upstream and AXEKZ write a single course byte followed by an i32 TP count.
    assert replay.replay_bytes[-5:] == b"\xff\x04\x03\x02\x01"
    parsed = parse_run_replay_bytes(data=replay.replay_bytes, source_name="run.replay")
    assert parsed.mode is mode
    assert parsed.course == 255
    assert parsed.teleports_used == 0x01020304


def test_all_truncated_headers_raise_domain_error() -> None:
    replay = build_synthetic_run_replay().replay_bytes
    for length in range(len(replay)):
        with pytest.raises(RunReplayParseError):
            parse_run_replay_bytes(data=replay[:length], source_name="truncated.replay")


@pytest.mark.parametrize("tickrate", [64.0, 100.0])
def test_strict_replay_rejects_non_128_tickrate(tickrate):
    replay = build_synthetic_run_replay(tickrate=tickrate, tick_count=1)
    with pytest.raises(RunReplayParseError):
        parse_run_replay_bytes(
            data=replay.replay_bytes + bytes(84), source_name="bad", validate_ticks=True
        )


@pytest.mark.parametrize("ticks", [b"", b"\x01\x00\x00\x00", b"\xff\xff\xff\xff"])
def test_strict_replay_rejects_missing_or_invalid_initial_tick(ticks):
    replay = build_synthetic_run_replay(tick_count=1)
    with pytest.raises(RunReplayParseError):
        parse_run_replay_bytes(
            data=replay.replay_bytes + ticks, source_name="bad", validate_ticks=True
        )
