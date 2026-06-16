"""add map review comment deleted notifications

Revision ID: 4f6a8b2c9d10
Revises: 7b8c9d0e1f23
Create Date: 2026-06-16 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "4f6a8b2c9d10"
down_revision = "7b8c9d0e1f23"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE player_notification_type ADD VALUE IF NOT EXISTS "
        "'map_review_comment_deleted'"
    )
    op.add_column(
        "player_notification",
        sa.Column("comment_text", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("player_notification", "comment_text")

    bind = op.get_bind()
    notification_type = postgresql.ENUM(
        "profile_like",
        "profile_comment",
        "player_follow",
        "wr_beaten",
        "player_report",
        name="player_notification_type",
    )

    op.execute(
        """
        DELETE FROM player_notification
        WHERE type = 'map_review_comment_deleted'::player_notification_type
        """
    )
    op.execute("ALTER TYPE player_notification_type RENAME TO player_notification_type_old")
    notification_type.create(bind, checkfirst=False)
    op.execute(
        """
        ALTER TABLE player_notification
        ALTER COLUMN type
        TYPE player_notification_type
        USING (type::text::player_notification_type)
        """
    )
    op.execute("DROP TYPE player_notification_type_old")
