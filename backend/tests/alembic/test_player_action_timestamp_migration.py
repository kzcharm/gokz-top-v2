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
        / "b1eb2523abfa_add_player_friends_and_action_timestamps.py"
    )
    spec = importlib.util.spec_from_file_location("player_action_timestamps", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _scratch_table_name(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def test_backfill_action_timestamps_maps_profile_fields_to_actions() -> None:
    migration = _load_migration_module()
    source_table = _scratch_table_name("test_profile_field_change")
    target_table = _scratch_table_name("test_player_action_timestamp")

    with Session(engine) as session:
        try:
            session.exec(
                text(
                    f"""
                    CREATE TABLE "{source_table}" (
                        player_steamid64 BIGINT NOT NULL,
                        field TEXT NOT NULL,
                        changed_at TIMESTAMPTZ NOT NULL
                    )
                    """
                )
            )
            session.exec(
                text(
                    f"""
                    CREATE TABLE "{target_table}" (
                        player_steamid64 BIGINT NOT NULL,
                        action player_action NOT NULL,
                        recorded_at TIMESTAMPTZ NOT NULL
                    )
                    """
                )
            )
            session.exec(
                text(
                    f"""
                    INSERT INTO "{source_table}" (
                        player_steamid64,
                        field,
                        changed_at
                    ) VALUES
                        (76561198000000011, 'alias', TIMESTAMPTZ '2026-03-01 00:00:00+00'),
                        (76561198000000022, 'custom_id', TIMESTAMPTZ '2026-03-02 00:00:00+00'),
                        (76561198000000033, 'country', TIMESTAMPTZ '2026-03-03 00:00:00+00')
                    """
                )
            )
            session.commit()

            migration._backfill_action_timestamps(
                session.connection(),
                source_table=source_table,
                target_table=target_table,
            )
            session.commit()

            rows = session.exec(
                text(
                    f"""
                    SELECT player_steamid64, action::text, recorded_at
                    FROM "{target_table}"
                    ORDER BY player_steamid64
                    """
                )
            ).all()

            assert rows == [
                (76561198000000011, "alias_change", rows[0].recorded_at),
                (76561198000000022, "custom_id_change", rows[1].recorded_at),
                (76561198000000033, "country_manual_override", rows[2].recorded_at),
            ]
            assert str(rows[0].recorded_at) == "2026-03-01 00:00:00+00:00"
            assert str(rows[1].recorded_at) == "2026-03-02 00:00:00+00:00"
            assert str(rows[2].recorded_at) == "2026-03-03 00:00:00+00:00"
        finally:
            session.exec(text(f'DROP TABLE IF EXISTS "{target_table}"'))
            session.exec(text(f'DROP TABLE IF EXISTS "{source_table}"'))
            session.commit()


def test_player_friend_and_action_timestamp_schema_exists() -> None:
    with Session(engine) as session:
        action_table = session.exec(
            text(
                """
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = 'player_action_timestamp'
                """
            )
        ).first()
        friend_table = session.exec(
            text(
                """
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = 'player_friend'
                """
            )
        ).first()
        visibility_column = session.exec(
            text(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'player'
                  AND column_name = 'friends_visibility'
                """
            )
        ).first()
        checked_at_column = session.exec(
            text(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'player'
                  AND column_name = 'friends_visibility_checked_at'
                """
            )
        ).first()

    assert action_table is not None
    assert friend_table is not None
    assert visibility_column is not None
    assert checked_at_column is not None
