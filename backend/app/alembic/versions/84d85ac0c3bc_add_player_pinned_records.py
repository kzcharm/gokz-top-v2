"""add player pinned records

Revision ID: 84d85ac0c3bc
Revises: 29dd29117244
Create Date: 2026-04-09 20:27:47.534131

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "84d85ac0c3bc"
down_revision = "29dd29117244"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_type
                WHERE typname = 'record_scope'
            ) THEN
                CREATE TYPE record_scope AS ENUM ('OVR', 'KZT', 'SKZ', 'VNL');
            END IF;
        END
        $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_type
                WHERE typname = 'record_type'
            ) THEN
                CREATE TYPE record_type AS ENUM ('NUB', 'PRO');
            END IF;
        END
        $$;
        """
    )
    op.execute(
        """
        CREATE TABLE player_pinned_record (
            id UUID NOT NULL,
            player_steamid64 BIGINT NOT NULL,
            map_id INTEGER NOT NULL,
            scope record_scope NOT NULL,
            type record_type NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (id),
            FOREIGN KEY (map_id) REFERENCES map (id) ON DELETE CASCADE,
            FOREIGN KEY (player_steamid64) REFERENCES player (steamid64) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_player_pinned_record_player_scope_created_at
        ON player_pinned_record (player_steamid64, scope, created_at)
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX ux_player_pinned_record_player_map_scope_type
        ON player_pinned_record (player_steamid64, map_id, scope, type)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_player_pinned_record_player_map_scope_type")
    op.execute("DROP INDEX IF EXISTS ix_player_pinned_record_player_scope_created_at")
    op.execute("DROP TABLE IF EXISTS player_pinned_record")
    op.execute("DROP TYPE IF EXISTS record_scope")
