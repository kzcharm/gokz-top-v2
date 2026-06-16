"""add player reports

Revision ID: 2c4d6e8f0a12
Revises: f7b3c9a1d2e4
Create Date: 2026-06-16 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "2c4d6e8f0a12"
down_revision = "f7b3c9a1d2e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE player_notification_type ADD VALUE IF NOT EXISTS 'player_report'"
    )
    op.create_table(
        "player_report",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("reporter_steamid64", sa.BigInteger(), nullable=False),
        sa.Column("target_steamid64", sa.BigInteger(), nullable=False),
        sa.Column("record_uuid", sa.Uuid(), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["record_uuid"],
            ["record.uuid"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["reporter_steamid64"],
            ["player.steamid64"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_steamid64"],
            ["player.steamid64"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_player_report_record_uuid",
        "player_report",
        ["record_uuid"],
        unique=False,
    )
    op.create_index(
        "ix_player_report_reporter_created_at",
        "player_report",
        ["reporter_steamid64", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_player_report_target_created_at",
        "player_report",
        ["target_steamid64", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_player_report_target_created_at", table_name="player_report")
    op.drop_index("ix_player_report_reporter_created_at", table_name="player_report")
    op.drop_index("ix_player_report_record_uuid", table_name="player_report")
    op.drop_table("player_report")

    bind = op.get_bind()
    notification_type = postgresql.ENUM(
        "profile_like",
        "profile_comment",
        "player_follow",
        "wr_beaten",
        name="player_notification_type",
    )

    op.execute(
        """
        DELETE FROM player_notification
        WHERE type = 'player_report'::player_notification_type
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
