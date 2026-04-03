"""add record filter table

Revision ID: 770aa37ba32f
Revises: 1931535c416e
Create Date: 2026-04-03 14:59:55.812576

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "770aa37ba32f"
down_revision = "1931535c416e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "record_filter",
        sa.Column("map_id", sa.Integer(), nullable=False),
        sa.Column("stage", sa.Integer(), nullable=False),
        sa.Column("mode_id", sa.Integer(), nullable=False),
        sa.Column("tickrate", sa.Integer(), nullable=False),
        sa.Column("has_teleports", sa.Boolean(), nullable=False),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by_id", sa.String(length=32), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["mode_id"], ["mode.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_record_filter_availability",
        "record_filter",
        ["stage", "mode_id", "map_id", "has_teleports", "id"],
        unique=False,
    )
    op.create_index(
        "ix_record_filter_lookup",
        "record_filter",
        ["map_id", "stage", "mode_id", "tickrate", "has_teleports", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_record_filter_lookup", table_name="record_filter")
    op.drop_index("ix_record_filter_availability", table_name="record_filter")
    op.drop_table("record_filter")
