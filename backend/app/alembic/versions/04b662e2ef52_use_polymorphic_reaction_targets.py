"""use polymorphic reaction targets

Revision ID: 04b662e2ef52
Revises: 17b460e10481
Create Date: 2026-09-22 16:11:46.862820

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "04b662e2ef52"
down_revision = "17b460e10481"
branch_labels = None
depends_on = None


OLD_TARGET_COLUMNS = (
    "media_post_id",
    "record_uuid",
    "map_review_id",
    "poll_id",
    "github_release_id",
)
OLD_TARGET_INDEXES = (
    ("ix_content_reaction_map_review", "map_review_id"),
    ("ix_content_reaction_media_post", "media_post_id"),
    ("ix_content_reaction_poll", "poll_id"),
    ("ix_content_reaction_record", "record_uuid"),
    ("ix_content_reaction_release", "github_release_id"),
)


def upgrade() -> None:
    op.add_column(
        "content_reaction",
        sa.Column("content_type", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "content_reaction",
        sa.Column("content_id", sa.String(length=64), nullable=True),
    )

    op.execute(
        sa.text(
            """
            UPDATE content_reaction
            SET content_type = CASE
                    WHEN media_post_id IS NOT NULL THEN 'media_post'
                    WHEN record_uuid IS NOT NULL THEN 'recent_wr'
                    WHEN map_review_id IS NOT NULL THEN 'map_review_comment'
                    WHEN poll_id IS NOT NULL THEN 'poll'
                    WHEN github_release_id IS NOT NULL THEN 'release'
                END,
                content_id = COALESCE(
                    media_post_id::text,
                    record_uuid::text,
                    map_review_id::text,
                    poll_id::text,
                    github_release_id::text
                )
            """
        )
    )

    op.alter_column(
        "content_reaction",
        "content_type",
        existing_type=sa.String(length=32),
        nullable=False,
    )
    op.alter_column(
        "content_reaction",
        "content_id",
        existing_type=sa.String(length=64),
        nullable=False,
    )

    op.drop_constraint(
        "ck_content_reaction_exactly_one_target",
        "content_reaction",
        type_="check",
    )
    for index_name, _ in OLD_TARGET_INDEXES:
        op.drop_index(index_name, table_name="content_reaction")
    op.drop_constraint(
        "uq_content_reaction_user_emoji_target",
        "content_reaction",
        type_="unique",
    )

    op.create_unique_constraint(
        "uq_content_reaction_user_emoji_target",
        "content_reaction",
        ["user_steamid64", "emoji_key", "content_type", "content_id"],
    )
    op.create_index(
        "ix_content_reaction_target",
        "content_reaction",
        ["content_type", "content_id", "emoji_key"],
        unique=False,
    )
    op.create_check_constraint(
        "ck_content_reaction_content_type",
        "content_reaction",
        "content_type IN "
        "('media_post', 'recent_wr', 'map_review_comment', 'poll', 'release')",
    )

    op.drop_constraint(
        "content_reaction_map_review_id_fkey",
        "content_reaction",
        type_="foreignkey",
    )
    op.drop_constraint(
        "content_reaction_record_uuid_fkey",
        "content_reaction",
        type_="foreignkey",
    )
    op.drop_constraint(
        "content_reaction_media_post_id_fkey",
        "content_reaction",
        type_="foreignkey",
    )
    op.drop_constraint(
        "content_reaction_github_release_id_fkey",
        "content_reaction",
        type_="foreignkey",
    )
    op.drop_constraint(
        "content_reaction_poll_id_fkey",
        "content_reaction",
        type_="foreignkey",
    )
    for column_name in OLD_TARGET_COLUMNS:
        op.drop_column("content_reaction", column_name)


def downgrade() -> None:
    op.add_column(
        "content_reaction",
        sa.Column("media_post_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "content_reaction",
        sa.Column("record_uuid", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "content_reaction",
        sa.Column("map_review_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "content_reaction",
        sa.Column("poll_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "content_reaction",
        sa.Column("github_release_id", sa.BigInteger(), nullable=True),
    )

    op.execute(
        sa.text(
            """
            UPDATE content_reaction
            SET media_post_id = CASE
                    WHEN content_type = 'media_post' THEN content_id::uuid
                END,
                record_uuid = CASE
                    WHEN content_type = 'recent_wr' THEN content_id::uuid
                END,
                map_review_id = CASE
                    WHEN content_type = 'map_review_comment' THEN content_id::uuid
                END,
                poll_id = CASE
                    WHEN content_type = 'poll' THEN content_id::uuid
                END,
                github_release_id = CASE
                    WHEN content_type = 'release' THEN content_id::bigint
                END
            """
        )
    )

    op.create_foreign_key(
        "content_reaction_map_review_id_fkey",
        "content_reaction",
        "map_review",
        ["map_review_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "content_reaction_record_uuid_fkey",
        "content_reaction",
        "record",
        ["record_uuid"],
        ["uuid"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "content_reaction_media_post_id_fkey",
        "content_reaction",
        "media_post",
        ["media_post_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "content_reaction_github_release_id_fkey",
        "content_reaction",
        "github_release",
        ["github_release_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "content_reaction_poll_id_fkey",
        "content_reaction",
        "poll",
        ["poll_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.drop_constraint(
        "ck_content_reaction_content_type",
        "content_reaction",
        type_="check",
    )
    op.drop_index("ix_content_reaction_target", table_name="content_reaction")
    op.drop_constraint(
        "uq_content_reaction_user_emoji_target",
        "content_reaction",
        type_="unique",
    )

    op.create_unique_constraint(
        "uq_content_reaction_user_emoji_target",
        "content_reaction",
        [
            "user_steamid64",
            "emoji_key",
            "media_post_id",
            "record_uuid",
            "map_review_id",
            "poll_id",
            "github_release_id",
        ],
        postgresql_nulls_not_distinct=True,
    )
    for index_name, column_name in OLD_TARGET_INDEXES:
        op.create_index(
            index_name,
            "content_reaction",
            [column_name, "emoji_key"],
            unique=False,
        )
    op.create_check_constraint(
        "ck_content_reaction_exactly_one_target",
        "content_reaction",
        "num_nonnulls(media_post_id, record_uuid, map_review_id, poll_id, "
        "github_release_id) = 1",
    )

    op.drop_column("content_reaction", "content_id")
    op.drop_column("content_reaction", "content_type")
