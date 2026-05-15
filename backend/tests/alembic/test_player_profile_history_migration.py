from sqlalchemy import text
from sqlmodel import Session

from app.core.db import engine


def test_player_profile_history_schema_exists() -> None:
    with Session(engine) as session:
        table_exists = session.exec(
            text(
                """
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = 'player_profile_history'
                """
            )
        ).first()
        index_exists = session.exec(
            text(
                """
                SELECT 1
                FROM pg_indexes
                WHERE schemaname = 'public'
                  AND indexname = 'ix_player_profile_history_player_steamid64_changed_at'
                """
            )
        ).first()
        constraint_exists = session.exec(
            text(
                """
                SELECT 1
                FROM information_schema.table_constraints
                WHERE table_schema = 'public'
                  AND table_name = 'player_profile_history'
                  AND constraint_name = 'ck_player_profile_history_name_or_avatar_present'
                  AND constraint_type = 'CHECK'
                """
            )
        ).first()

    assert table_exists is not None
    assert index_exists is not None
    assert constraint_exists is not None
