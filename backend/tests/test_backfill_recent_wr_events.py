from pathlib import Path

import pytest

from app.backfill_recent_wr_events import _build_parser, _main_async


def test_recent_wr_migration_is_schema_only() -> None:
    migration = (
        Path(__file__).parents[1]
        / "app/alembic/versions/d74ff38d65bd_add_recent_wr_event_cache.py"
    ).read_text()

    lowered = migration.lower()
    assert "op.create_table" in migration
    assert "insert into" not in lowered
    assert "select " not in lowered
    assert "record as" not in lowered


def test_recent_wr_backfill_cli_supports_safe_operational_modes() -> None:
    parser = _build_parser()

    dry_run = parser.parse_args(["--dry-run", "--batch-size", "7"])
    repair = parser.parse_args(["--course-id", "42"])
    reset = parser.parse_args(["--reset-progress"])

    assert dry_run.dry_run is True
    assert dry_run.batch_size == 7
    assert repair.course_id == 42
    assert reset.reset_progress is True


@pytest.mark.parametrize("value", ["0", "-1"])
@pytest.mark.asyncio
async def test_recent_wr_backfill_rejects_non_positive_batch_size(
    value: str,
) -> None:
    with pytest.raises(ValueError, match="batch-size"):
        await _main_async(["--batch-size", value])

def test_recent_wr_backfill_has_no_database_retention_limit() -> None:
    parser = _build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["--limit-per-scope", "100"])
