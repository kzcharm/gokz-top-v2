"""add record moderation audit tables

Revision ID: 76bec12252fc
Revises: 9a7e1cb8db39
Create Date: 2026-05-25 14:48:41.891527

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "76bec12252fc"
down_revision = "9a7e1cb8db39"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "record_moderation_action",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor_steamid64", sa.BigInteger(), nullable=False),
        sa.Column("action_type", sa.String(length=32), nullable=False),
        sa.Column("target_record_uuid", sa.Uuid(), nullable=True),
        sa.Column("target_player_steamid64", sa.BigInteger(), nullable=True),
        sa.Column("target_map_id", sa.Integer(), nullable=True),
        sa.Column("target_stage", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_steamid64"], ["user.steamid64"]),
        sa.ForeignKeyConstraint(["target_map_id"], ["map.id"]),
        sa.ForeignKeyConstraint(["target_player_steamid64"], ["player.steamid64"]),
        sa.ForeignKeyConstraint(["target_record_uuid"], ["record.uuid"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_record_moderation_action_actor_created_at",
        "record_moderation_action",
        ["actor_steamid64", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_record_moderation_action_target_map_stage_created_at",
        "record_moderation_action",
        ["target_map_id", "target_stage", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_record_moderation_action_target_player_created_at",
        "record_moderation_action",
        ["target_player_steamid64", "created_at"],
        unique=False,
    )

    op.create_table(
        "record_moderation_action_record",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("action_id", sa.Uuid(), nullable=False),
        sa.Column("record_uuid", sa.Uuid(), nullable=False),
        sa.Column("record_id", sa.Integer(), nullable=True),
        sa.Column("player_steamid64", sa.BigInteger(), nullable=False),
        sa.Column("map_id", sa.Integer(), nullable=False),
        sa.Column("stage", sa.Integer(), nullable=False),
        sa.Column("before_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["action_id"], ["record_moderation_action.id"]),
        sa.ForeignKeyConstraint(["map_id"], ["map.id"]),
        sa.ForeignKeyConstraint(["player_steamid64"], ["player.steamid64"]),
        sa.ForeignKeyConstraint(["record_uuid"], ["record.uuid"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_record_moderation_action_record_action_id",
        "record_moderation_action_record",
        ["action_id"],
        unique=False,
    )
    op.create_index(
        "ix_record_moderation_action_record_record_uuid",
        "record_moderation_action_record",
        ["record_uuid"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_record_moderation_action_record_record_uuid",
        table_name="record_moderation_action_record",
    )
    op.drop_index(
        "ix_record_moderation_action_record_action_id",
        table_name="record_moderation_action_record",
    )
    op.drop_table("record_moderation_action_record")

    op.drop_index(
        "ix_record_moderation_action_target_player_created_at",
        table_name="record_moderation_action",
    )
    op.drop_index(
        "ix_record_moderation_action_target_map_stage_created_at",
        table_name="record_moderation_action",
    )
    op.drop_index(
        "ix_record_moderation_action_actor_created_at",
        table_name="record_moderation_action",
    )
    op.drop_table("record_moderation_action")
