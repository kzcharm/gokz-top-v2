"""add player friends and action timestamps

Revision ID: b1eb2523abfa
Revises: 46ea19a73892
Create Date: 2026-05-13 18:03:03.740070

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Connection

# revision identifiers, used by Alembic.
revision = "b1eb2523abfa"
down_revision = "46ea19a73892"
branch_labels = None
depends_on = None

player_action_enum = postgresql.ENUM(
    "alias_change",
    "custom_id_change",
    "country_manual_override",
    "friends_sync",
    name="player_action",
)
player_friends_visibility_enum = postgresql.ENUM(
    "public",
    "private_profile",
    "private_friends",
    name="player_friends_visibility",
)
player_profile_field_enum = postgresql.ENUM(
    "alias",
    "custom_id",
    "country",
    name="player_profile_field",
)


def _backfill_action_timestamps(
    connection: Connection,
    source_table: str = "player_profile_field_change",
    target_table: str = "player_action_timestamp",
) -> None:
    connection.execute(
        sa.text(
            f"""
            INSERT INTO "{target_table}" (
                player_steamid64,
                action,
                recorded_at
            )
            SELECT
                player_steamid64,
                CASE field::text
                    WHEN 'alias' THEN 'alias_change'
                    WHEN 'custom_id' THEN 'custom_id_change'
                    WHEN 'country' THEN 'country_manual_override'
                END::player_action,
                changed_at
            FROM "{source_table}"
            """
        )
    )


def _restore_profile_field_changes(
    connection: Connection,
    source_table: str = "player_action_timestamp",
    target_table: str = "player_profile_field_change",
) -> None:
    connection.execute(
        sa.text(
            f"""
            INSERT INTO "{target_table}" (
                player_steamid64,
                field,
                changed_at
            )
            SELECT
                player_steamid64,
                CASE action::text
                    WHEN 'alias_change' THEN 'alias'
                    WHEN 'custom_id_change' THEN 'custom_id'
                    WHEN 'country_manual_override' THEN 'country'
                END::player_profile_field,
                recorded_at
            FROM "{source_table}"
            WHERE action IN (
                'alias_change',
                'custom_id_change',
                'country_manual_override'
            )
            """
        )
    )


def upgrade() -> None:
    bind = op.get_bind()

    player_action_enum.create(bind, checkfirst=True)
    player_friends_visibility_enum.create(bind, checkfirst=True)

    op.create_table(
        "player_action_timestamp",
        sa.Column("player_steamid64", sa.BigInteger(), nullable=False),
        sa.Column(
            "action",
            postgresql.ENUM(
                "alias_change",
                "custom_id_change",
                "country_manual_override",
                "friends_sync",
                name="player_action",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["player_steamid64"],
            ["player.steamid64"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("player_steamid64", "action"),
    )
    _backfill_action_timestamps(bind)

    op.create_table(
        "player_friend",
        sa.Column("player_steamid64", sa.BigInteger(), nullable=False),
        sa.Column("friend_steamid64", sa.BigInteger(), nullable=False),
        sa.Column("friend_since", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["friend_steamid64"],
            ["player.steamid64"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["player_steamid64"],
            ["player.steamid64"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("player_steamid64", "friend_steamid64"),
    )
    op.create_index(
        "ix_player_friend_friend_steamid64",
        "player_friend",
        ["friend_steamid64"],
        unique=False,
    )

    op.add_column(
        "player",
        sa.Column(
            "friends_visibility",
            postgresql.ENUM(
                "public",
                "private_profile",
                "private_friends",
                name="player_friends_visibility",
                create_type=False,
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "player",
        sa.Column("friends_visibility_checked_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.drop_table("player_profile_field_change")
    player_profile_field_enum.drop(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()

    player_profile_field_enum.create(bind, checkfirst=True)
    op.create_table(
        "player_profile_field_change",
        sa.Column("player_steamid64", sa.BigInteger(), nullable=False),
        sa.Column(
            "field",
            postgresql.ENUM(
                "alias",
                "custom_id",
                "country",
                name="player_profile_field",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["player_steamid64"],
            ["player.steamid64"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("player_steamid64", "field"),
    )
    _restore_profile_field_changes(bind)

    op.drop_column("player", "friends_visibility_checked_at")
    op.drop_column("player", "friends_visibility")
    op.drop_index("ix_player_friend_friend_steamid64", table_name="player_friend")
    op.drop_table("player_friend")
    op.drop_table("player_action_timestamp")
    player_friends_visibility_enum.drop(bind, checkfirst=True)
    player_action_enum.drop(bind, checkfirst=True)
