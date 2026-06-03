"""add player notifications

Revision ID: a5705b4a3358
Revises: 3f77c5f3aa2b
Create Date: 2026-06-03 11:51:59.515338

"""

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "a5705b4a3358"
down_revision = "3f77c5f3aa2b"
branch_labels = None
depends_on = None


notification_type = postgresql.ENUM(
    "profile_like",
    "profile_comment",
    "player_follow",
    "wr_beaten",
    name="player_notification_type",
)

notification_type_existing = postgresql.ENUM(
    "profile_like",
    "profile_comment",
    "player_follow",
    "wr_beaten",
    name="player_notification_type",
    create_type=False,
)

mode_scope = postgresql.ENUM(
    "OVR",
    "KZT",
    "SKZ",
    "VNL",
    name="mode_scope",
    create_type=False,
)

record_type = postgresql.ENUM(
    "NUB",
    "PRO",
    name="record_type",
    create_type=False,
)


def upgrade() -> None:
    notification_type.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "player_notification",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("recipient_steamid64", sa.BigInteger(), nullable=False),
        sa.Column("actor_steamid64", sa.BigInteger(), nullable=True),
        sa.Column("type", notification_type_existing, nullable=False),
        sa.Column("source_key", sa.String(length=255), nullable=False),
        sa.Column("target_url", sa.Text(), nullable=False),
        sa.Column("target_player_steamid64", sa.BigInteger(), nullable=True),
        sa.Column("comment_id", sa.Uuid(), nullable=True),
        sa.Column(
            "comment_preview",
            sqlmodel.sql.sqltypes.AutoString(length=140),
            nullable=True,
        ),
        sa.Column("map_id", sa.Integer(), nullable=True),
        sa.Column(
            "map_name",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=True,
        ),
        sa.Column("scope", mode_scope, nullable=True),
        sa.Column("record_type", record_type, nullable=True),
        sa.Column("previous_record_uuid", sa.Uuid(), nullable=True),
        sa.Column("new_record_uuid", sa.Uuid(), nullable=True),
        sa.Column("new_record_time", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["actor_steamid64"],
            ["player.steamid64"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["map_id"], ["map.id"]),
        sa.ForeignKeyConstraint(
            ["recipient_steamid64"],
            ["player.steamid64"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_player_notification_recipient_created_at",
        "player_notification",
        ["recipient_steamid64", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_player_notification_recipient_read_at_created_at",
        "player_notification",
        ["recipient_steamid64", "read_at", "created_at"],
        unique=False,
    )
    op.create_index(
        "ux_player_notification_source_key",
        "player_notification",
        ["source_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ux_player_notification_source_key",
        table_name="player_notification",
    )
    op.drop_index(
        "ix_player_notification_recipient_read_at_created_at",
        table_name="player_notification",
    )
    op.drop_index(
        "ix_player_notification_recipient_created_at",
        table_name="player_notification",
    )
    op.drop_table("player_notification")
    notification_type.drop(op.get_bind(), checkfirst=True)
