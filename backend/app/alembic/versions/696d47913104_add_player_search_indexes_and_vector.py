"""add player search indexes and vector

Revision ID: 696d47913104
Revises: b9c0461664a5
Create Date: 2026-04-06 21:05:35.822992

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "696d47913104"
down_revision = "b9c0461664a5"
branch_labels = None
depends_on = None

PLAYER_SEARCH_VECTOR_SQL = """
setweight(to_tsvector('simple', coalesce(custom_id, '')), 'A') ||
setweight(to_tsvector('simple', coalesce(alias, '')), 'A') ||
setweight(to_tsvector('simple', coalesce(name, '')), 'B')
"""


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.execute(
        """
        WITH ranked_custom_ids AS (
            SELECT
                steamid64,
                custom_id,
                row_number() OVER (
                    PARTITION BY custom_id
                    ORDER BY steamid64 ASC
                ) AS row_num
            FROM player
            WHERE custom_id IS NOT NULL
        )
        UPDATE player
        SET custom_id = NULL
        FROM ranked_custom_ids
        WHERE player.steamid64 = ranked_custom_ids.steamid64
          AND ranked_custom_ids.row_num > 1
        """
    )

    op.add_column(
        "player",
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(PLAYER_SEARCH_VECTOR_SQL, persisted=True),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_player_search_vector",
        "player",
        ["search_vector"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "ix_player_name_trgm",
        "player",
        [sa.literal_column("lower(name) gin_trgm_ops")],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "ix_player_alias_trgm",
        "player",
        [sa.literal_column("lower(coalesce(alias, '')) gin_trgm_ops")],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "ix_player_custom_id_trgm",
        "player",
        [sa.literal_column("lower(coalesce(custom_id, '')) gin_trgm_ops")],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "ux_player_custom_id_not_null",
        "player",
        ["custom_id"],
        unique=True,
        postgresql_where=sa.text("custom_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ux_player_custom_id_not_null",
        table_name="player",
        postgresql_where=sa.text("custom_id IS NOT NULL"),
    )
    op.drop_index("ix_player_custom_id_trgm", table_name="player", postgresql_using="gin")
    op.drop_index("ix_player_alias_trgm", table_name="player", postgresql_using="gin")
    op.drop_index("ix_player_name_trgm", table_name="player", postgresql_using="gin")
    op.drop_index("ix_player_search_vector", table_name="player", postgresql_using="gin")
    op.drop_column("player", "search_vector")
