import importlib.util
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlmodel import Session

from app.core.db import engine


def _load_migration_module() -> Any:
    path = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "alembic"
        / "versions"
        / "f3fdc0b9d339_add_player_profile_field_changes.py"
    )
    spec = importlib.util.spec_from_file_location("profile_field_changes", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _scratch_table_name(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def test_backfill_country_locks_creates_country_field_change_rows() -> None:
    migration = _load_migration_module()
    player_table = _scratch_table_name("test_profile_field_player")
    field_change_table = _scratch_table_name("test_profile_field_change")

    with Session(engine) as session:
        try:
            session.exec(
                text(
                    """
                    CREATE TYPE player_profile_field AS ENUM (
                        'alias',
                        'custom_id',
                        'country'
                    )
                    """
                )
            )
            session.exec(
                text(
                    f"""
                    CREATE TABLE "{player_table}" (
                        steamid64 BIGINT PRIMARY KEY,
                        is_country_locked BOOLEAN NOT NULL,
                        created_at TIMESTAMPTZ NULL,
                        updated_at TIMESTAMPTZ NULL
                    )
                    """
                )
            )
            session.exec(
                text(
                    f"""
                    CREATE TABLE "{field_change_table}" (
                        player_steamid64 BIGINT NOT NULL,
                        field player_profile_field NOT NULL,
                        changed_at TIMESTAMPTZ NOT NULL,
                        PRIMARY KEY (player_steamid64, field)
                    )
                    """
                )
            )
            session.exec(
                text(
                    f"""
                    INSERT INTO "{player_table}" (
                        steamid64,
                        is_country_locked,
                        created_at,
                        updated_at
                    ) VALUES
                        (
                            76561198000000011,
                            TRUE,
                            TIMESTAMPTZ '2026-03-01 00:00:00+00',
                            TIMESTAMPTZ '2026-03-02 00:00:00+00'
                        ),
                        (
                            76561198000000022,
                            TRUE,
                            TIMESTAMPTZ '2026-04-01 00:00:00+00',
                            NULL
                        ),
                        (
                            76561198000000033,
                            FALSE,
                            TIMESTAMPTZ '2026-05-01 00:00:00+00',
                            TIMESTAMPTZ '2026-05-02 00:00:00+00'
                        )
                    """
                )
            )
            session.commit()

            migration._backfill_country_field_changes(
                session.connection(),
                player_table=player_table,
                field_change_table=field_change_table,
            )
            session.commit()

            rows = session.exec(
                text(
                    f"""
                    SELECT player_steamid64, field::text, changed_at
                    FROM "{field_change_table}"
                    ORDER BY player_steamid64
                    """
                )
            ).all()

            assert len(rows) == 2
            assert rows[0].player_steamid64 == 76561198000000011
            assert rows[0].field == "country"
            assert str(rows[0].changed_at) == "2026-03-02 00:00:00+00:00"
            assert rows[1].player_steamid64 == 76561198000000022
            assert rows[1].field == "country"
            assert str(rows[1].changed_at) == "2026-04-01 00:00:00+00:00"
        finally:
            session.exec(text(f'DROP TABLE IF EXISTS "{field_change_table}"'))
            session.exec(text(f'DROP TABLE IF EXISTS "{player_table}"'))
            session.exec(text("DROP TYPE IF EXISTS player_profile_field"))
            session.commit()


def test_player_country_lock_column_is_removed_after_later_migrations() -> None:
    with Session(engine) as session:
        removed_column = session.exec(
            text(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'player'
                  AND column_name = 'is_country_locked'
                """
            )
        ).first()
        field_change_table = session.exec(
            text(
                """
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = 'player_profile_field_change'
                """
            )
        ).first()
        action_timestamp_table = session.exec(
            text(
                """
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = 'player_action_timestamp'
                """
            )
        ).first()

    assert removed_column is None
    assert field_change_table is None
    assert action_timestamp_table is not None
