"""add content reactions and release cache

Revision ID: 17b460e10481
Revises: f2be7377c455
Create Date: 2026-09-22 14:35:55.625231
"""

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op

revision = "17b460e10481"
down_revision = "f2be7377c455"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "github_release",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column(
            "tag_name", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False
        ),
        sa.Column(
            "name", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True
        ),
        sa.Column(
            "html_url",
            sqlmodel.sql.sqltypes.AutoString(length=1000),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("is_listed", sa.Boolean(), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "content_reaction",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_steamid64", sa.BigInteger(), nullable=False),
        sa.Column(
            "emoji_key",
            sqlmodel.sql.sqltypes.AutoString(length=128),
            nullable=False,
        ),
        sa.Column("media_post_id", sa.Uuid(), nullable=True),
        sa.Column("record_uuid", sa.Uuid(), nullable=True),
        sa.Column("map_review_id", sa.Uuid(), nullable=True),
        sa.Column("poll_id", sa.Uuid(), nullable=True),
        sa.Column("github_release_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "num_nonnulls(media_post_id, record_uuid, map_review_id, poll_id, github_release_id) = 1",
            name="ck_content_reaction_exactly_one_target",
        ),
        sa.ForeignKeyConstraint(
            ["github_release_id"], ["github_release.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["map_review_id"], ["map_review.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["media_post_id"], ["media_post.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["poll_id"], ["poll.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["record_uuid"], ["record.uuid"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_steamid64"], ["user.steamid64"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_steamid64",
            "emoji_key",
            "media_post_id",
            "record_uuid",
            "map_review_id",
            "poll_id",
            "github_release_id",
            name="uq_content_reaction_user_emoji_target",
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index(
        "ix_content_reaction_map_review",
        "content_reaction",
        ["map_review_id", "emoji_key"],
    )
    op.create_index(
        "ix_content_reaction_media_post",
        "content_reaction",
        ["media_post_id", "emoji_key"],
    )
    op.create_index(
        "ix_content_reaction_poll",
        "content_reaction",
        ["poll_id", "emoji_key"],
    )
    op.create_index(
        "ix_content_reaction_record",
        "content_reaction",
        ["record_uuid", "emoji_key"],
    )
    op.create_index(
        "ix_content_reaction_release",
        "content_reaction",
        ["github_release_id", "emoji_key"],
    )


def downgrade() -> None:
    op.drop_index("ix_content_reaction_release", table_name="content_reaction")
    op.drop_index("ix_content_reaction_record", table_name="content_reaction")
    op.drop_index("ix_content_reaction_poll", table_name="content_reaction")
    op.drop_index("ix_content_reaction_media_post", table_name="content_reaction")
    op.drop_index("ix_content_reaction_map_review", table_name="content_reaction")
    op.drop_table("content_reaction")
    op.drop_table("github_release")
