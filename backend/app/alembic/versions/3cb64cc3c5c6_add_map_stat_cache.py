"""add map stat cache

Revision ID: 3cb64cc3c5c6
Revises: a33e61ef01d2
Create Date: 2026-05-23 15:35:33.161449

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "3cb64cc3c5c6"
down_revision = "a33e61ef01d2"
branch_labels = None
depends_on = None


map_stat_type = postgresql.ENUM(
    "wr_gap_distribution",
    name="map_stat_type",
)
map_stat_type_existing = postgresql.ENUM(
    "wr_gap_distribution",
    name="map_stat_type",
    create_type=False,
)


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS cache")
    map_stat_type.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "map_stat",
        sa.Column("map_id", sa.Integer(), nullable=False),
        sa.Column(
            "scope",
            postgresql.ENUM(
                "OVR",
                "KZT",
                "SKZ",
                "VNL",
                name="mode_scope",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "record_type",
            postgresql.ENUM(
                "NUB",
                "PRO",
                name="record_type",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("type", map_stat_type_existing, nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["map_id"], ["map.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("map_id", "scope", "record_type", "type"),
        schema="cache",
    )


def downgrade() -> None:
    op.drop_table("map_stat", schema="cache")
    map_stat_type.drop(op.get_bind(), checkfirst=True)
