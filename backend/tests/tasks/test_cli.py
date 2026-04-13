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


@dataclass(frozen=True, slots=True)
class _ProfileResult:
    selected: int
    created: int
    updated: int
    skipped: int


def test_cli_root_help() -> None:
    runner = CliRunner()

    result = runner.invoke(cli.app, ["--help"])

    assert result.exit_code == 0
    assert "build" in result.output
    assert "sync" in result.output
    assert "GOKZ.TOP backend operator CLI" in result.output


def test_cli_build_help() -> None:
    runner = CliRunner()

    result = runner.invoke(cli.app, ["build", "--help"])

    assert result.exit_code == 0
    assert "rating" in result.output
    assert "points" in result.output
    assert "profile" not in result.output


def test_cli_sync_help() -> None:
    runner = CliRunner()

    result = runner.invoke(cli.app, ["sync", "--help"])

    assert result.exit_code == 0
    assert "profiles" in result.output


def test_cli_sync_profiles_help() -> None:
    runner = CliRunner()

    result = runner.invoke(cli.app, ["sync", "profiles", "--help"])

    assert result.exit_code == 0
    assert "--missing-avatar" in result.output
    assert "--stale-days" in result.output
    assert "--leaderboard" in result.output


def test_cli_sync_profiles_defaults_to_all_players(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    captured: dict[str, object] = {}

    async def _fake_rebuild_player_profiles(**kwargs: object) -> _ProfileResult:
        captured.update(kwargs)
        return _ProfileResult(selected=3, created=0, updated=3, skipped=0)

    monkeypatch.setattr(
        "app.cli.profile_task.rebuild_player_profiles",
        _fake_rebuild_player_profiles,
    )

    result = runner.invoke(cli.app, ["sync", "profiles"])

    assert result.exit_code == 0
    assert captured["only_missing_avatar"] is False
    assert captured["leaderboard_scope"] is None
    assert captured["stale_days"] is None
    assert "Profile Sync Complete" in result.output


def test_cli_sync_profiles_rejects_multiple_selection_filters() -> None:
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        ["sync", "profiles", "--missing-avatar", "--stale-days", "30"],
    )

    assert result.exit_code != 0
    assert "Use only one of --missing-avatar, --stale-days, or --leaderboard." in result.output


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


def test_cli_rating_accepts_lowercase_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    captured: dict[str, object] = {}

    async def _fake_rebuild_ratings(**kwargs: object) -> _RatingResult:
        captured.update(kwargs)
        return _RatingResult(
            full=False,
            pb_points_updated=0,
            leaderboard=_LeaderboardResult(selected=0, created=0, updated=0),
        )

    monkeypatch.setattr("app.cli.rating_task.rebuild_ratings", _fake_rebuild_ratings)

    result = runner.invoke(cli.app, ["build", "rating", "--scope", "ovr"])

    assert result.exit_code == 0
    assert captured["scope_ids"] == [0]


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
