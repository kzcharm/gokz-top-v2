"""rename record scope to mode scope

Revision ID: 5dd433939640
Revises: e1a2c3f4b5d6
Create Date: 2026-04-14 21:57:09.560685

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "5dd433939640"
down_revision = "e1a2c3f4b5d6"
branch_labels = None
depends_on = None


def _ensure_mode_scope_type() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_type
                WHERE typname = 'record_scope'
            ) AND NOT EXISTS (
                SELECT 1
                FROM pg_type
                WHERE typname = 'mode_scope'
            ) THEN
                ALTER TYPE record_scope RENAME TO mode_scope;
            ELSIF NOT EXISTS (
                SELECT 1
                FROM pg_type
                WHERE typname = 'mode_scope'
            ) THEN
                CREATE TYPE mode_scope AS ENUM ('OVR', 'KZT', 'SKZ', 'VNL');
            END IF;
        END
        $$;
        """
    )


def upgrade() -> None:
    _ensure_mode_scope_type()

    op.execute(
        """
        ALTER TABLE leaderboard_player
        ALTER COLUMN scope TYPE mode_scope
        USING (
            CASE scope
                WHEN 0 THEN 'OVR'
                WHEN 1 THEN 'KZT'
                WHEN 2 THEN 'SKZ'
                WHEN 3 THEN 'VNL'
                ELSE NULL
            END
        )::mode_scope
        """
    )
    op.execute(
        """
        ALTER TABLE leaderboard_player_count
        ALTER COLUMN scope DROP DEFAULT
        """
    )
    op.execute(
        """
        ALTER TABLE leaderboard_player_count
        ALTER COLUMN scope TYPE mode_scope
        USING (
            CASE scope
                WHEN 0 THEN 'OVR'
                WHEN 1 THEN 'KZT'
                WHEN 2 THEN 'SKZ'
                WHEN 3 THEN 'VNL'
                ELSE NULL
            END
        )::mode_scope
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE leaderboard_player
        ALTER COLUMN scope TYPE SMALLINT
        USING (
            CASE scope::text
                WHEN 'OVR' THEN 0
                WHEN 'KZT' THEN 1
                WHEN 'SKZ' THEN 2
                WHEN 'VNL' THEN 3
                ELSE NULL
            END
        )
        """
    )
    op.execute(
        """
        ALTER TABLE leaderboard_player_count
        ALTER COLUMN scope TYPE SMALLINT
        USING (
            CASE scope::text
                WHEN 'OVR' THEN 0
                WHEN 'KZT' THEN 1
                WHEN 'SKZ' THEN 2
                WHEN 'VNL' THEN 3
                ELSE NULL
            END
        )
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_type
                WHERE typname = 'mode_scope'
            ) AND NOT EXISTS (
                SELECT 1
                FROM pg_type
                WHERE typname = 'record_scope'
            ) THEN
                ALTER TYPE mode_scope RENAME TO record_scope;
            END IF;
        END
        $$;
        """
    )
