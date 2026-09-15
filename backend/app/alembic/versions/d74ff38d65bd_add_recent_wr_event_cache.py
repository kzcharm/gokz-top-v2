"""add recent wr event cache

Revision ID: d74ff38d65bd
Revises: 56d1eea4dfea
Create Date: 2026-09-15 15:56:10.723629

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d74ff38d65bd"
down_revision = "56d1eea4dfea"
branch_labels = None
depends_on = None


def upgrade() -> None:
    mode_scope = postgresql.ENUM(
        "OVR", "KZT", "SKZ", "VNL", name="mode_scope", create_type=False
    )
    record_type = postgresql.ENUM("NUB", "PRO", name="record_type", create_type=False)
    op.create_table(
        "recent_wr_events",
        sa.Column("record_uuid", sa.Uuid(), nullable=False),
        sa.Column(
            "scope",
            mode_scope,
            nullable=False,
        ),
        sa.Column(
            "type",
            record_type,
            nullable=False,
        ),
        sa.Column("map_id", sa.Integer(), nullable=False),
        sa.Column("previous_record_uuid", sa.Uuid(), nullable=True),
        sa.Column("previous_time", sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column("event_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["map_id"], ["map.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["record_uuid"], ["record.uuid"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("record_uuid", "scope", "type"),
        schema="cache",
    )
    op.create_index(
        "ix_cache_recent_wr_events_map_scope_type",
        "recent_wr_events",
        ["map_id", "scope", "type"],
        schema="cache",
    )
    op.create_index(
        "ix_cache_recent_wr_events_scope_created_at",
        "recent_wr_events",
        ["scope", sa.text("event_created_at DESC"), sa.text("record_uuid DESC")],
        schema="cache",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_cache_recent_wr_events_scope_created_at",
        table_name="recent_wr_events",
        schema="cache",
    )
    op.drop_index(
        "ix_cache_recent_wr_events_map_scope_type",
        table_name="recent_wr_events",
        schema="cache",
    )
    op.drop_table("recent_wr_events", schema="cache")
