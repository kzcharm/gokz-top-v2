"""add map reviews

Revision ID: e34188d48951
Revises: 6a2f9c4d1b7e
Create Date: 2026-04-08 21:00:52.833222

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "e34188d48951"
down_revision = "6a2f9c4d1b7e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "map_review",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("steamid64", sa.BigInteger(), nullable=False),
        sa.Column("map_id", sa.Integer(), nullable=False),
        sa.Column("server_group_id", sa.Uuid(), nullable=True),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["map_id"], ["map.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["server_group_id"],
            ["server_group.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["steamid64"], ["player.steamid64"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "steamid64",
            "map_id",
            "server_group_id",
            name="uq_map_review_context",
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index(
        "ix_map_review_map_id_steamid64_updated_at",
        "map_review",
        ["map_id", "steamid64", "updated_at"],
        unique=False,
    )
    op.create_index(
        "ix_map_review_server_group_id_updated_at",
        "map_review",
        ["server_group_id", "updated_at"],
        unique=False,
    )
    op.create_index(
        "ix_map_review_steamid64_map_id_updated_at",
        "map_review",
        ["steamid64", "map_id", "updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_map_review_steamid64_map_id_updated_at",
        table_name="map_review",
    )
    op.drop_index(
        "ix_map_review_server_group_id_updated_at",
        table_name="map_review",
    )
    op.drop_index(
        "ix_map_review_map_id_steamid64_updated_at",
        table_name="map_review",
    )
    op.drop_table("map_review")
