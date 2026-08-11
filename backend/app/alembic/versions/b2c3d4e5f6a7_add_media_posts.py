"""add cached bilibili media posts

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "media_post",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("player_social_link_id", sa.Uuid(), nullable=False),
        sa.Column("player_steamid64", sa.BigInteger(), nullable=False),
        sa.Column("platform", postgresql.ENUM("bilibili", "github", "twitch", "x", "youtube", name="player_social_platform", create_type=False), nullable=False),
        sa.Column("external_video_id", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("thumbnail_url", sa.String(length=1000), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("available", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(["player_social_link_id"], ["player_social_link.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["player_steamid64"], ["player.steamid64"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ux_media_post_platform_external_id", "media_post", ["platform", "external_video_id"], unique=True)
    op.create_index("ix_media_post_published_at_id", "media_post", ["published_at", "id"])
    op.create_index("ix_media_post_player_published_at", "media_post", ["player_steamid64", "published_at"])


def downgrade() -> None:
    op.drop_index("ix_media_post_player_published_at", table_name="media_post")
    op.drop_index("ix_media_post_published_at_id", table_name="media_post")
    op.drop_index("ux_media_post_platform_external_id", table_name="media_post")
    op.drop_table("media_post")
