"""add live stream state

Revision ID: d8e7d8bab509
Revises: f3fdc0b9d339
Create Date: 2026-05-07 16:00:12.814833

"""

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = "d8e7d8bab509"
down_revision = "f3fdc0b9d339"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "live_stream_state",
        sa.Column("social_link_id", sa.Uuid(), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_live", sa.Boolean(), nullable=False),
        sa.Column("last_live_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_live_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "last_stream_url",
            sqlmodel.sql.sqltypes.AutoString(length=500),
            nullable=True,
        ),
        sa.Column(
            "last_stream_title",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=True,
        ),
        sa.Column(
            "last_preview_image_url",
            sqlmodel.sql.sqltypes.AutoString(length=1000),
            nullable=True,
        ),
        sa.Column(
            "last_channel_display_name",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=True,
        ),
        sa.Column("last_viewer_count", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["social_link_id"],
            ["player_social_link.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("social_link_id"),
    )
    op.create_index(
        "ix_live_stream_state_is_live",
        "live_stream_state",
        ["is_live"],
        unique=False,
    )
    op.create_index(
        "ix_live_stream_state_last_checked_at",
        "live_stream_state",
        ["last_checked_at"],
        unique=False,
    )
    op.create_index(
        "ix_live_stream_state_last_live_seen_at",
        "live_stream_state",
        ["last_live_seen_at"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_live_stream_state_last_live_seen_at",
        table_name="live_stream_state",
    )
    op.drop_index(
        "ix_live_stream_state_last_checked_at",
        table_name="live_stream_state",
    )
    op.drop_index("ix_live_stream_state_is_live", table_name="live_stream_state")
    op.drop_table("live_stream_state")
