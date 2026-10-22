"""Operator commands must render their results and expose safe preview modes."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

from typer.testing import CliRunner

from app import cli
from app.core import db as database
from app.models import MapFileDistributionSyncResult, ModeScope
from app.services.map_authors import MapAuthorSeedResult
from app.services.skill_rating_converter import (
    TIED_TOP_DISPLAY_RATING,
    TOP_DISPLAY_RATING,
    Calibration,
)
from app.tasks.build.skill_rating_converters import CalibrationResult


def test_cli_calibration_report_labels_unique_and_tied_leaders(monkeypatch) -> None:
    results = [
        CalibrationResult(
            scope=ModeScope.KZT,
            skill="bhop",
            population=5,
            positive=4,
            ties=0,
            calibration=Calibration(
                [[0, 0], [100, 1], [200, TOP_DISPLAY_RATING]], 5, 4, 0
            ),
        ),
        CalibrationResult(
            scope=ModeScope.KZT,
            skill="climb",
            population=5,
            positive=4,
            ties=1,
            calibration=Calibration([[0, 0], [100, TIED_TOP_DISPLAY_RATING]], 5, 4, 1),
        ),
        CalibrationResult(
            scope=ModeScope.KZT,
            skill="ladder",
            population=5,
            positive=0,
            ties=4,
            calibration=None,
        ),
    ]
    operation = AsyncMock(return_value=results)
    monkeypatch.setattr(
        cli.skill_converter_task, "calibrate_skill_converters", operation
    )
    result = CliRunner().invoke(
        cli.app, ["build", "skill-converters", "--scope", "kzt", "--save"]
    )
    assert result.exit_code == 0, result.output
    assert "saved" in result.output and "KZT" in result.output
    assert "unique" in result.output and "tie" in result.output
    assert "No positive" in result.output
    assert operation.await_args.kwargs == {"scopes": (ModeScope.KZT,), "save": True}


def test_cli_skill_and_point_summaries_and_pb_preview(monkeypatch) -> None:
    monkeypatch.setattr(
        cli.skill_ratings_task,
        "rebuild_all_skill_ratings",
        AsyncMock(return_value={ModeScope.KZT: 3}),
    )
    result = CliRunner().invoke(
        cli.app, ["build", "skill-ratings", "--scope", "KZT", "--limit", "3"]
    )
    assert result.exit_code == 0, result.output
    assert "Total rows updated" in result.output
    points = AsyncMock(return_value=4)
    monkeypatch.setattr(cli.points_task, "rebuild_record_pb_points", points)
    result = CliRunner().invoke(
        cli.app, ["build", "points", "--scope", "KZT", "--all-stages"]
    )
    assert result.exit_code == 0, result.output
    assert "Points Build Complete" in result.output
    assert points.await_args.kwargs["stage"] is None
    monkeypatch.setattr(
        cli.pb_task, "list_record_pb_buckets", AsyncMock(return_value=[])
    )
    rebuild = AsyncMock()
    monkeypatch.setattr(cli.pb_task, "rebuild_record_pbs", rebuild)
    result = CliRunner().invoke(cli.app, ["build", "pb", "--list-only"])
    assert result.exit_code == 0, result.output
    assert "No record_pb buckets need rebuilding" in result.output
    rebuild.assert_not_awaited()


def test_cli_map_maintenance_summaries(monkeypatch) -> None:
    @asynccontextmanager
    async def session_factory():
        yield object()

    monkeypatch.setattr(database, "async_session_maker", session_factory)
    monkeypatch.setattr(
        cli,
        "seed_map_authors_from_kz_map_info",
        AsyncMock(
            return_value=MapAuthorSeedResult(
                processed=3, matched=2, updated=1, skipped=1
            )
        ),
    )
    result = CliRunner().invoke(cli.app, ["sync", "map-authors"])
    assert result.exit_code == 0, result.output
    assert "Map Author Seed Complete" in result.output
    monkeypatch.setattr(
        cli,
        "sync_map_files",
        AsyncMock(return_value=MapFileDistributionSyncResult(processed=2, uploaded=1)),
    )
    result = CliRunner().invoke(cli.app, ["map-files", "sync", "--force"])
    assert result.exit_code == 0, result.output
    assert "Map File Sync Complete" in result.output


def test_cli_transfer_default_is_a_dry_run_with_an_audit_summary(
    monkeypatch, tmp_path
) -> None:
    from app.tasks.record_transfer import RecordTransferResult

    operation = AsyncMock(
        return_value=RecordTransferResult(
            source_steamid64=123,
            target_steamid64=456,
            dry_run=True,
            audit_path=tmp_path / "audit.jsonl",
            summary_path=tmp_path / "summary.json",
            source_records_before=2,
            target_records_before=1,
            source_records_after=2,
            target_records_after=1,
            transferred_records=2,
            touched_pb_keys=4,
            touched_courses=1,
            source_record_pb_after=2,
            leaderboard_created=0,
            leaderboard_updated=0,
            player_stats_deleted=0,
            checksum="audit-checksum",
            rating_rows_selected=0,
            rating_rows_created=0,
            rating_rows_updated=0,
        )
    )
    monkeypatch.setattr(cli.record_transfer_task, "transfer_records", operation)
    result = CliRunner().invoke(
        cli.app,
        [
            "transfer",
            "records",
            "--source-steamid64",
            "123",
            "--target-steamid64",
            "456",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Dry Run" in result.output and "audit-checksum" in result.output
    assert operation.await_args.kwargs["dry_run"] is True


def test_cli_interruptions_exit_130_and_show_partial_progress(monkeypatch) -> None:
    monkeypatch.setattr(
        cli.profile_task,
        "rebuild_player_profiles",
        AsyncMock(
            side_effect=cli.profile_task.RebuildPlayerProfileInterruptedError(
                cli.profile_task.RebuildPlayerProfileResult(selected=3, updated=1)
            )
        ),
    )
    result = CliRunner().invoke(cli.app, ["sync", "profiles", "--steamid64", "123"])
    assert result.exit_code == 130, result.output
    assert "Profile Sync Interrupted" in result.output
    monkeypatch.setattr(
        cli.friends_task,
        "sync_player_friends_for_players",
        AsyncMock(
            side_effect=cli.friends_task.SyncPlayerFriendsInterruptedError(
                cli.friends_task.SyncPlayerFriendsResult(selected=3, synced=1)
            )
        ),
    )
    result = CliRunner().invoke(cli.app, ["sync", "friends", "--steamid64", "123"])
    assert result.exit_code == 130, result.output
    assert "Friends Sync Interrupted" in result.output
