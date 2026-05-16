from decimal import Decimal

import pytest

from app.models import JumpstatType, KZMode
from app.services.jump_replay_parser import (
    JumpReplayParseError,
    parse_jump_replay_bytes,
)
from tests.utils.jump_replay import (
    build_synthetic_jump_replay,
    expected_parent_values,
    expected_strafe_stats,
)


def test_parse_jump_replay_bytes_returns_expected_jumpstat_values() -> None:
    synthetic = build_synthetic_jump_replay()

    parsed = parse_jump_replay_bytes(
        data=synthetic.replay_bytes,
        source_name="synthetic.replay",
    )

    assert parsed.steamid64 == synthetic.steamid64
    assert parsed.jumped_at == synthetic.jumped_at
    assert parsed.mode == KZMode.KZT
    assert parsed.type == JumpstatType.LJ
    assert parsed.strafe_stats == expected_strafe_stats()

    expected = expected_parent_values()
    assert parsed.distance == expected["distance"]
    assert parsed.block == expected["block"]
    assert parsed.strafes == expected["strafes"]
    assert parsed.sync_percent == expected["sync_percent"]
    assert parsed.pre_speed == expected["pre_speed"]
    assert parsed.max_speed == expected["max_speed"]
    assert parsed.w_count == expected["w_count"]
    assert parsed.overlap_count == expected["overlap_count"]
    assert parsed.dead_air_count == expected["dead_air_count"]
    assert parsed.width == expected["width"]
    assert parsed.height == expected["height"]
    assert parsed.airtime_percent == expected["airtime_percent"]
    assert parsed.offset == expected["offset"]
    assert parsed.deviation == expected["deviation"]
    assert parsed.crouched_ticks == expected["crouched_ticks"]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"magic": 0xDEADBEEF}, "invalid replay magic"),
        ({"version": 1}, "unsupported replay version"),
        ({"replay_type": 0}, "not a jump replay"),
        ({"style_index": 1}, "unsupported replay style"),
        ({"mode_index": 9}, "unsupported replay mode"),
        ({"jump_type_index": 99}, "unsupported jump type"),
    ],
)
def test_parse_jump_replay_bytes_rejects_unsupported_replays(
    kwargs: dict[str, int],
    message: str,
) -> None:
    synthetic = build_synthetic_jump_replay(**kwargs)

    with pytest.raises(JumpReplayParseError, match=message):
        parse_jump_replay_bytes(
            data=synthetic.replay_bytes,
            source_name="invalid.replay",
        )


def test_parse_jump_replay_bytes_preserves_non_block_deviation() -> None:
    synthetic = build_synthetic_jump_replay(block_distance=0)

    parsed = parse_jump_replay_bytes(
        data=synthetic.replay_bytes,
        source_name="non-block.replay",
    )

    assert parsed.block is None
    assert parsed.deviation == Decimal("2.0000")


def test_parse_jump_replay_bytes_supports_nkz_mode() -> None:
    synthetic = build_synthetic_jump_replay(mode_index=3)

    parsed = parse_jump_replay_bytes(
        data=synthetic.replay_bytes,
        source_name="nkz.replay",
    )

    assert parsed.mode == KZMode.NKZ


def test_parse_jump_replay_bytes_rejects_truncated_replay() -> None:
    with pytest.raises(JumpReplayParseError, match="truncated or malformed replay"):
        parse_jump_replay_bytes(data=b"", source_name="empty.replay")
