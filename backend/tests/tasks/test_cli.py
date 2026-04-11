from dataclasses import dataclass

import pytest
from typer.testing import CliRunner

from app import cli


@dataclass(frozen=True, slots=True)
class _LeaderboardResult:
    selected: int
    created: int
    updated: int


@dataclass(frozen=True, slots=True)
class _RatingResult:
    full: bool
    pb_points_updated: int
    leaderboard: _LeaderboardResult


def test_cli_root_help() -> None:
    runner = CliRunner()

    result = runner.invoke(cli.app, ["--help"])

    assert result.exit_code == 0
    assert "build" in result.output
    assert "GOKZ.TOP backend operator CLI" in result.output


def test_cli_build_help() -> None:
    runner = CliRunner()

    result = runner.invoke(cli.app, ["build", "--help"])

    assert result.exit_code == 0
    assert "rating" in result.output
    assert "points" in result.output
    assert "profile" in result.output


def test_cli_rating_help() -> None:
    runner = CliRunner()

    result = runner.invoke(cli.app, ["build", "rating", "--help"])

    assert result.exit_code == 0
    assert "--full" in result.output
    assert "--scope" in result.output


def test_cli_rating_full_dispatches_full_rebuild(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    captured: dict[str, object] = {}

    async def _fake_rebuild_ratings(**kwargs: object) -> _RatingResult:
        captured.update(kwargs)
        return _RatingResult(
            full=True,
            pb_points_updated=12,
            leaderboard=_LeaderboardResult(selected=3, created=1, updated=2),
        )

    monkeypatch.setattr("app.cli.rating_task.rebuild_ratings", _fake_rebuild_ratings)

    result = runner.invoke(cli.app, ["build", "rating", "--full", "--scope", "KZT"])

    assert result.exit_code == 0
    assert captured["full"] is True
    assert "PB points updated" in result.output


def test_cli_pb_and_pbs_share_the_same_impl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    calls: list[dict[str, object]] = []

    def _fake_build_pb_impl(**kwargs: object) -> None:
        calls.append(dict(kwargs))

    monkeypatch.setattr(cli, "_build_pb_impl", _fake_build_pb_impl)

    pb_result = runner.invoke(cli.app, ["build", "pb", "--force-all"])
    pbs_result = runner.invoke(cli.app, ["build", "pbs", "--force-all"])

    assert pb_result.exit_code == 0
    assert pbs_result.exit_code == 0
    assert calls == [
        {
            "list_only": False,
            "force_all": True,
            "limit": None,
            "analyze": False,
            "ensure_map_courses": False,
        },
        {
            "list_only": False,
            "force_all": True,
            "limit": None,
            "analyze": False,
            "ensure_map_courses": False,
        },
    ]


def test_cli_rejects_invalid_scope() -> None:
    runner = CliRunner()

    result = runner.invoke(cli.app, ["build", "rating", "--scope", "BAD"])

    assert result.exit_code != 0
    assert "Invalid scope" in result.output
