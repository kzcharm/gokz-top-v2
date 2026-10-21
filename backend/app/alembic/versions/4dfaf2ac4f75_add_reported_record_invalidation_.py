"""add reported record invalidation notifications

Revision ID: 4dfaf2ac4f75
Revises: 89e9355f393f
Create Date: 2026-10-21 23:04:09.379136

"""

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "4dfaf2ac4f75"
down_revision = "89e9355f393f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Autogenerate does not detect additions to PostgreSQL enums.
    op.execute(
        "ALTER TYPE player_notification_type ADD VALUE IF NOT EXISTS "
        "'reported_record_invalidated'"
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM player_notification "
        "WHERE type = 'reported_record_invalidated'::player_notification_type"
    )
    op.execute(
        "ALTER TYPE player_notification_type RENAME TO player_notification_type_old"
    )
    notification_type = postgresql.ENUM(
        "profile_like",
        "profile_comment",
        "player_follow",
        "wr_beaten",
        "player_report",
        "map_review_comment_deleted",
        name="player_notification_type",
    )
    notification_type.create(op.get_bind(), checkfirst=False)
    op.execute(
        "ALTER TABLE player_notification ALTER COLUMN type "
        "TYPE player_notification_type USING (type::text::player_notification_type)"
    )
    op.execute("DROP TYPE player_notification_type_old")
