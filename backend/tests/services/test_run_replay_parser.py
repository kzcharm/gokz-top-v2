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
