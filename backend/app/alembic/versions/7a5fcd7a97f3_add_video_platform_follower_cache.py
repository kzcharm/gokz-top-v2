"""add video platform follower cache

Revision ID: 7a5fcd7a97f3
Revises: c7f2b8a9d1e4
Create Date: 2026-05-31 15:33:48.887478

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "7a5fcd7a97f3"
down_revision = "c7f2b8a9d1e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS cache")
    op.create_table(
        "player_video_platform_followers",
        sa.Column("social_link_id", sa.Uuid(), nullable=False),
        sa.Column("player_steamid64", sa.BigInteger(), nullable=False),
        sa.Column(
            "platform",
            postgresql.ENUM(
                "BILIBILI",
                "GITHUB",
                "TWITCH",
                "X",
                "YOUTUBE",
                name="player_social_platform",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("account_identifier", sa.String(length=128), nullable=False),
        sa.Column("follower_count", sa.Integer(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_attempted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["player_steamid64"],
            ["player.steamid64"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["social_link_id"],
            ["player_social_link.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("social_link_id"),
        schema="cache",
    )
    op.create_index(
        op.f("ix_cache_player_video_platform_followers_platform"),
        "player_video_platform_followers",
        ["platform"],
        unique=False,
        schema="cache",
    )
    op.create_index(
        op.f("ix_cache_player_video_platform_followers_player_steamid64"),
        "player_video_platform_followers",
        ["player_steamid64"],
        unique=False,
        schema="cache",
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_cache_player_video_platform_followers_player_steamid64"),
        table_name="player_video_platform_followers",
        schema="cache",
    )
    op.drop_index(
        op.f("ix_cache_player_video_platform_followers_platform"),
        table_name="player_video_platform_followers",
        schema="cache",
    )
    op.drop_table("player_video_platform_followers", schema="cache")
