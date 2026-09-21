import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from app import cli

_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def _plain_output(output: str) -> str:
    return _ANSI_RE.sub("", output)


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


@dataclass(frozen=True, slots=True)
class _FriendsResult:
    selected: int
    synced: int
    rate_limited: int
    private: int
    failed: int


def test_cli_root_help() -> None:
    runner = CliRunner()

    result = runner.invoke(cli.app, ["--help"])

    assert result.exit_code == 0
    assert "build" in result.output
    assert "rebuild" in result.output
    assert "sync" in result.output
    assert "export" in result.output
    assert "GOKZ.TOP backend operator CLI" in result.output


def test_cli_export_records_dispatches_filters(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}
    output_path = tmp_path / "axe-records.csv.gz"

    async def _fake_export_records_to_csv(
        **kwargs: object,
    ) -> cli.record_csv_export_service.RecordCsvExportResult:
        captured.update(kwargs)
        return cli.record_csv_export_service.RecordCsvExportResult(
            output_path=output_path,
            server_ids=(1633, 1683),
            after=datetime(2026, 1, 1, tzinfo=UTC),
            before=datetime(2026, 1, 31, 23, 59, 59, 999999, tzinfo=UTC),
            exported_rows=509_006,
            skipped_invalid_rows=9,
            skipped_bad_steamid_rows=4,
            compressed_size=8_000_000,
        )

    monkeypatch.setattr(
        cli.record_csv_export_service,
        "export_records_to_csv",
        _fake_export_records_to_csv,
    )

    result = CliRunner().invoke(
        cli.app,
        [
            "export",
            "records",
            "--server-id",
            "1683",
            "--server-id",
            "1633",
            "--after",
            "2026-01-01",
            "--before",
            "2026-01-31",
            "--output",
            str(output_path),
        ],
    )

    assert result.exit_code == 0
    assert captured == {
        "output_path": output_path,
        "server_ids": [1683, 1633],
        "server_groups": None,
        "after": "2026-01-01",
        "before": "2026-01-31",
        "force": False,
    }
    assert "Record CSV Export Complete" in _plain_output(result.output)
    assert "509006" in _plain_output(result.output).replace(",", "")


def test_cli_export_players_dispatches_group_filter(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}
    output_path = tmp_path / "axe-players.csv.gz"

    async def _fake_export_players_to_csv(
        **kwargs: object,
    ) -> cli.player_csv_export_service.PlayerCsvExportResult:
        captured.update(kwargs)
        return cli.player_csv_export_service.PlayerCsvExportResult(
            output_path=output_path,
            server_ids=(1633, 1683),
            after=None,
            before=None,
            exported_players=3_778,
            compressed_size=200_000,
        )

    monkeypatch.setattr(
        cli.player_csv_export_service,
        "export_players_to_csv",
        _fake_export_players_to_csv,
    )

    result = CliRunner().invoke(
        cli.app,
        [
            "export",
            "players",
            "--server-group",
            "axe",
            "--output",
            str(output_path),
        ],
    )

    assert result.exit_code == 0
    assert captured == {
        "output_path": output_path,
        "server_ids": None,
        "server_groups": ["axe"],
        "after": None,
        "before": None,
        "force": False,
    }
    assert "Player CSV Export Complete" in _plain_output(result.output)
    assert "3778" in _plain_output(result.output).replace(",", "")


def test_cli_build_help() -> None:
    runner = CliRunner()

    result = runner.invoke(cli.app, ["build", "--help"])

    assert result.exit_code == 0
    assert "rating" in result.output
    assert "points" in result.output
    assert "profile" not in result.output


def test_cli_rebuild_help() -> None:
    runner = CliRunner()

    result = runner.invoke(cli.app, ["rebuild", "--help"])

    assert result.exit_code == 0
    assert "maps" in result.output


def test_cli_rebuild_maps_dispatches_filters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    captured: dict[str, object] = {}

    async def _fake_rebuild_map_leaderboards(**kwargs: object) -> object:
        captured.update(kwargs)
        return type(
            "_MapRebuildResult",
            (),
            {
                "scopes": (cli.ModeScope.KZT,),
                "map_ids": (123, 456),
                "rows_rebuilt": 2,
            },
        )()

    monkeypatch.setattr(
        "app.cli.maps_task.rebuild_map_leaderboards",
        _fake_rebuild_map_leaderboards,
    )

    result = runner.invoke(
        cli.app,
        ["rebuild", "maps", "--scope", "kzt", "--map-id", "123", "--map-id", "456"],
    )

    assert result.exit_code == 0
    assert captured["scopes"] == (cli.ModeScope.KZT,)
    assert captured["map_ids"] == [123, 456]
    assert "Maps Rebuild Complete" in result.output
    assert "Rows rebuilt" in result.output


def test_cli_sync_media_dispatches_reclassification_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    captured: dict[str, object] = {}

    class _SessionContext:
        async def __aenter__(self) -> object:
            return object()

        async def __aexit__(self, *_: object) -> None:
            return None

    async def _fake_reclassify_media_posts(
        **kwargs: object,
    ) -> cli.MediaReclassificationResult:
        captured.update(kwargs)
        return cli.MediaReclassificationResult(
            inspected=2,
            matched_by_reason=Counter({cli.MediaMatchReason.TAG: 1}),
            rejected=1,
            unchanged=0,
            failed=0,
            dry_run=True,
        )

    monkeypatch.setattr(
        "app.core.db.async_session_maker", lambda: _SessionContext()
    )
    monkeypatch.setattr(cli, "reclassify_media_posts", _fake_reclassify_media_posts)

    result = runner.invoke(
        cli.app,
        [
            "sync",
            "media",
            "--reclassify-existing",
            "--platform",
            "youtube",
            "--limit",
            "2",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    assert captured["platform"] == cli.PlayerSocialPlatform.YOUTUBE
    assert captured["limit"] == 2
    assert captured["dry_run"] is True
    assert "Media Reclassification Dry Run" in _plain_output(result.output)
    assert "Matched: tag" in _plain_output(result.output)


def test_cli_sync_media_requires_explicit_reclassification_flag() -> None:
    result = CliRunner().invoke(cli.app, ["sync", "media"])

    assert result.exit_code != 0
    assert "--reclassify-existing" in _plain_output(result.output)


def test_cli_sync_help() -> None:
    runner = CliRunner()

    result = runner.invoke(cli.app, ["sync", "--help"])

    assert result.exit_code == 0
    assert "profiles" in result.output


def test_cli_sync_profiles_help() -> None:
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        ["sync", "profiles", "--help"],
        terminal_width=160,
    )

    assert result.exit_code == 0
    output = _plain_output(result.output)
    assert "--missing-avatar" in output
    assert "--stale-days" in output
    assert "--leaderboard" in output


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
        terminal_width=160,
    )

    assert result.exit_code != 0
    output = _plain_output(result.output)
    assert "Use only one of --missing-avatar, --stale-days, or" in output
    assert "--leaderboard." in output


def test_cli_sync_friends_help() -> None:
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        ["sync", "friends", "--help"],
        terminal_width=160,
    )

    assert result.exit_code == 0
    output = _plain_output(result.output)
    assert "--steamid64" in output
    assert "--leaderboard" in output


def test_cli_sync_friends_dispatches_filters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    captured: dict[str, object] = {}

    async def _fake_sync_player_friends_for_players(
        **kwargs: object,
    ) -> _FriendsResult:
        captured.update(kwargs)
        return _FriendsResult(
            selected=2,
            synced=1,
            rate_limited=0,
            private=1,
            failed=0,
        )

    monkeypatch.setattr(
        "app.cli.friends_task.sync_player_friends_for_players",
        _fake_sync_player_friends_for_players,
    )

    result = runner.invoke(
        cli.app,
        ["sync", "friends", "--leaderboard", "kzt", "--limit", "5"],
    )

    assert result.exit_code == 0
    assert captured["leaderboard_scope"] == cli.ModeScope.KZT
    assert captured["limit"] == 5
    assert "Friends Sync Complete" in result.output


def test_cli_rating_help() -> None:
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        ["build", "rating", "--help"],
        terminal_width=160,
    )

    assert result.exit_code == 0
    output = _plain_output(result.output)
    assert "--full" in output
    assert "--scope" in output


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
