"""Add map table

Revision ID: 3a8c1f4e2d10
Revises: 2ff47bc7f5f2
Create Date: 2026-03-09 22:40:00.000000

"""

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "3a8c1f4e2d10"
down_revision = "2ff47bc7f5f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "map",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
        sa.Column("filesize", sa.Integer(), nullable=False),
        sa.Column("validated", sa.Boolean(), nullable=False),
        sa.Column("difficulty", sa.Integer(), nullable=False),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_by_steamid64", sa.BigInteger(), nullable=False),
        sa.Column("workshop_id", sa.BigInteger(), nullable=True),
        sa.Column("authors", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "no_steamid_names",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("difficulty >= 0 AND difficulty <= 8", name="ck_map_difficulty_range"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_map_name"),
    )

    op.create_index(op.f("ix_map_name"), "map", ["name"], unique=False)
    op.create_index("ix_map_validated", "map", ["validated"], unique=False)
    op.create_index("ix_map_difficulty", "map", ["difficulty"], unique=False)
    op.create_index("ix_map_created_on", "map", ["created_on"], unique=False)
    op.create_index("ix_map_updated_on", "map", ["updated_on"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_map_updated_on", table_name="map")
    op.drop_index("ix_map_created_on", table_name="map")
    op.drop_index("ix_map_difficulty", table_name="map")
    op.drop_index("ix_map_validated", table_name="map")
    op.drop_index(op.f("ix_map_name"), table_name="map")
    op.drop_table("map")
