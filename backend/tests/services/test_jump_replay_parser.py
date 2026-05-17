from decimal import Decimal

import pytest

from app.models import JumpstatType, KZMode
from app.services.jump_replay_parser import (
    JUMPSTAT_VISUALIZATION_VERSION,
    JumpReplayParseError,
    parse_jump_replay_bytes,
    parse_jump_replay_visualization,
)
from tests.utils.jump_replay import (
    RP_FL_ONGROUND,
    RP_IN_FORWARD,
    RP_IN_MOVERIGHT,
    SyntheticReplayTick,
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


def test_parse_jump_replay_bytes_rejects_non_finite_tick_values() -> None:
    synthetic = build_synthetic_jump_replay(
        ticks=[
            SyntheticReplayTick(
                origin=(0.0, 0.0, 0.0),
                angles=(0.0, 0.0, 0.0),
                velocity=(100.0, 0.0, 0.0),
                flags=RP_FL_ONGROUND | RP_IN_FORWARD,
                forwardmove=450.0,
            ),
            SyntheticReplayTick(
                origin=(1.0, 0.0, 1.0),
                angles=(0.0, float("inf"), 0.0),
                velocity=(110.0, 0.0, 10.0),
                flags=RP_IN_MOVERIGHT,
                sidemove=450.0,
            ),
            SyntheticReplayTick(
                origin=(2.0, 0.0, 0.0),
                angles=(0.0, 10.0, 0.0),
                velocity=(100.0, 0.0, -10.0),
                flags=RP_FL_ONGROUND | RP_IN_MOVERIGHT,
                sidemove=450.0,
            ),
        ]
    )

    with pytest.raises(JumpReplayParseError, match="non-finite angles.y"):
        parse_jump_replay_bytes(
            data=synthetic.replay_bytes,
            source_name="non-finite.replay",
        )


def test_parse_jump_replay_visualization_keeps_route_bottom_to_top() -> None:
    synthetic = build_synthetic_jump_replay()

    visualization = parse_jump_replay_visualization(
        data=synthetic.replay_bytes,
        source_name="synthetic.replay",
    )

    assert visualization.version == JUMPSTAT_VISUALIZATION_VERSION
    assert visualization.jump_direction == "FORWARDS"
    assert visualization.deviation_angle == pytest.approx(11.3099, abs=1e-4)
    assert len(visualization.samples) == 4
    assert visualization.samples[0].strafe_type == "NONE_RIGHT"
    assert visualization.samples[0].yaw_delta == -5.0
    assert visualization.samples[0].mouse_direction == "LEFT"
    assert visualization.samples[1].strafe_type == "LEFT"
    assert visualization.samples[1].a_pressed is True
    assert visualization.samples[1].d_pressed is False
    assert visualization.samples[1].mouse_direction == "RIGHT"
    assert visualization.samples[-1].mouse_direction == "NONE"
    assert visualization.samples[-1].yaw_delta == 0.0
    assert visualization.samples[0].x == pytest.approx(0.0, abs=1e-4)
    assert visualization.samples[0].y == pytest.approx(1.0, abs=1e-4)
    assert visualization.samples[-1].x == pytest.approx(-2.0, abs=1e-4)
    assert visualization.samples[-1].y == pytest.approx(10.0, abs=1e-4)


@pytest.mark.parametrize(
    ("ticks", "expected_direction", "expected_strafe_type", "expect_a", "expect_d"),
    [
        (
            [
                SyntheticReplayTick(
                    origin=(0.0, 0.0, 0.0),
                    angles=(0.0, 180.0, 0.0),
                    velocity=(100.0, 0.0, 0.0),
                    flags=RP_FL_ONGROUND | RP_IN_FORWARD,
                ),
                SyntheticReplayTick(
                    origin=(1.0, 0.0, 1.0),
                    angles=(0.0, 190.0, 0.0),
                    velocity=(110.0, 0.0, 10.0),
                    flags=RP_IN_MOVERIGHT,
                    sidemove=450.0,
                ),
                SyntheticReplayTick(
                    origin=(2.0, 0.0, 0.0),
                    angles=(0.0, 200.0, 0.0),
                    velocity=(100.0, 0.0, -10.0),
                    flags=RP_FL_ONGROUND | RP_IN_MOVERIGHT,
                    sidemove=450.0,
                ),
            ],
            "BACKWARDS",
            "LEFT",
            True,
            False,
        ),
        (
            [
                SyntheticReplayTick(
                    origin=(0.0, 0.0, 0.0),
                    angles=(0.0, -90.0, 0.0),
                    velocity=(100.0, 0.0, 0.0),
                    flags=RP_FL_ONGROUND | RP_IN_FORWARD,
                ),
                SyntheticReplayTick(
                    origin=(0.0, 1.0, 1.0),
                    angles=(0.0, -80.0, 0.0),
                    velocity=(100.0, 10.0, 10.0),
                    flags=RP_IN_FORWARD,
                    forwardmove=450.0,
                ),
                SyntheticReplayTick(
                    origin=(0.0, 2.0, 0.0),
                    angles=(0.0, -70.0, 0.0),
                    velocity=(100.0, 0.0, -10.0),
                    flags=RP_FL_ONGROUND | RP_IN_FORWARD,
                    forwardmove=450.0,
                ),
            ],
            "LEFT",
            "RIGHT",
            False,
            True,
        ),
    ],
)
def test_parse_jump_replay_visualization_classifies_directional_inputs(
    ticks: list[SyntheticReplayTick],
    expected_direction: str,
    expected_strafe_type: str,
    expect_a: bool,
    expect_d: bool,
) -> None:
    synthetic = build_synthetic_jump_replay(ticks=ticks)

    visualization = parse_jump_replay_visualization(
        data=synthetic.replay_bytes,
        source_name="directional.replay",
    )

    assert visualization.jump_direction == expected_direction
    assert visualization.samples[0].strafe_type == expected_strafe_type
    assert visualization.samples[0].a_pressed is expect_a
    assert visualization.samples[0].d_pressed is expect_d
