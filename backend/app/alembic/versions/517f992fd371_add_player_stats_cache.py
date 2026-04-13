"""add player stats cache

Revision ID: 517f992fd371
Revises: 11d5fd5344a3
Create Date: 2026-04-13 16:24:48.285565

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "517f992fd371"
down_revision = "11d5fd5344a3"
branch_labels = None
depends_on = None


player_stat_type = postgresql.ENUM(
    "daily_activity",
    name="player_stat_type",
)
player_stat_type_existing = postgresql.ENUM(
    "daily_activity",
    name="player_stat_type",
    create_type=False,
)


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS cache")
    player_stat_type.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "player_stats",
        sa.Column("steamid64", sa.BigInteger(), nullable=False),
        sa.Column("type", player_stat_type_existing, nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["steamid64"],
            ["player.steamid64"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("steamid64", "type"),
        schema="cache",
    )


def downgrade() -> None:
    op.drop_table("player_stats", schema="cache")
    player_stat_type.drop(op.get_bind(), checkfirst=True)
