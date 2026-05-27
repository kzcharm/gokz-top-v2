"""Reference players instead of users

Revision ID: b2f6c8d9e0a1
Revises: a0b1c2d3e4f5
Create Date: 2026-05-27 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "b2f6c8d9e0a1"
down_revision = "a0b1c2d3e4f5"
branch_labels = None
depends_on = None


def _backfill_referenced_players() -> None:
    op.execute(
        """
        INSERT INTO player (steamid64, name, created_at, updated_at)
        SELECT DISTINCT steamid64, steamid64::text, now(), now()
        FROM (
            SELECT viewer_steamid64 AS steamid64 FROM player_like
            UNION
            SELECT viewer_steamid64 AS steamid64 FROM player_profile_view
            UNION
            SELECT follower_steamid64 AS steamid64 FROM player_follow
            UNION
            SELECT actor_steamid64 AS steamid64 FROM record_moderation_action
            UNION
            SELECT owner_steamid64 AS steamid64 FROM server_group
            UNION
            SELECT user_steamid64 AS steamid64 FROM player_webhook
            UNION
            SELECT NULLIF(owner_steamid64, 0) AS steamid64 FROM server_globalapi
            UNION
            SELECT NULLIF(approved_by_steamid64, 0) AS steamid64 FROM server_globalapi
        ) AS referenced_players
        WHERE steamid64 IS NOT NULL
        ON CONFLICT (steamid64) DO NOTHING
        """
    )


def upgrade() -> None:
    _backfill_referenced_players()

    op.alter_column(
        "server_globalapi",
        "owner_steamid64",
        existing_type=sa.BigInteger(),
        nullable=True,
    )
    op.alter_column(
        "server_globalapi",
        "approved_by_steamid64",
        existing_type=sa.BigInteger(),
        nullable=True,
    )
    op.execute("UPDATE server_globalapi SET owner_steamid64 = NULL WHERE owner_steamid64 = 0")
    op.execute(
        "UPDATE server_globalapi SET approved_by_steamid64 = NULL "
        "WHERE approved_by_steamid64 = 0"
    )

    op.drop_constraint(
        "player_like_viewer_steamid64_fkey",
        "player_like",
        type_="foreignkey",
    )
    op.drop_constraint(
        "playerprofileview_viewer_steamid64_fkey",
        "player_profile_view",
        type_="foreignkey",
    )
    op.drop_constraint(
        "player_follow_follower_steamid64_fkey",
        "player_follow",
        type_="foreignkey",
    )
    op.drop_constraint(
        "record_moderation_action_actor_steamid64_fkey",
        "record_moderation_action",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_server_group_owner_steamid64_user",
        "server_group",
        type_="foreignkey",
    )
    op.drop_constraint(
        "player_webhook_user_steamid64_fkey",
        "player_webhook",
        type_="foreignkey",
    )

    op.alter_column(
        "player_webhook",
        "user_steamid64",
        new_column_name="player_steamid64",
        existing_type=sa.BigInteger(),
        existing_nullable=False,
    )
    op.create_foreign_key(
        "fk_player_like_viewer_steamid64_player",
        "player_like",
        "player",
        ["viewer_steamid64"],
        ["steamid64"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_player_profile_view_viewer_steamid64_player",
        "player_profile_view",
        "player",
        ["viewer_steamid64"],
        ["steamid64"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_player_follow_follower_steamid64_player",
        "player_follow",
        "player",
        ["follower_steamid64"],
        ["steamid64"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_record_moderation_action_actor_steamid64_player",
        "record_moderation_action",
        "player",
        ["actor_steamid64"],
        ["steamid64"],
    )
    op.create_foreign_key(
        "fk_server_group_owner_steamid64_player",
        "server_group",
        "player",
        ["owner_steamid64"],
        ["steamid64"],
    )
    op.create_foreign_key(
        "fk_player_webhook_player_steamid64_player",
        "player_webhook",
        "player",
        ["player_steamid64"],
        ["steamid64"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_server_globalapi_owner_steamid64_player",
        "server_globalapi",
        "player",
        ["owner_steamid64"],
        ["steamid64"],
    )
    op.create_foreign_key(
        "fk_server_globalapi_approved_by_steamid64_player",
        "server_globalapi",
        "player",
        ["approved_by_steamid64"],
        ["steamid64"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_server_globalapi_approved_by_steamid64_player",
        "server_globalapi",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_server_globalapi_owner_steamid64_player",
        "server_globalapi",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_player_webhook_player_steamid64_player",
        "player_webhook",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_server_group_owner_steamid64_player",
        "server_group",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_record_moderation_action_actor_steamid64_player",
        "record_moderation_action",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_player_follow_follower_steamid64_player",
        "player_follow",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_player_profile_view_viewer_steamid64_player",
        "player_profile_view",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_player_like_viewer_steamid64_player",
        "player_like",
        type_="foreignkey",
    )

    op.alter_column(
        "player_webhook",
        "player_steamid64",
        new_column_name="user_steamid64",
        existing_type=sa.BigInteger(),
        existing_nullable=False,
    )

    op.execute("UPDATE server_globalapi SET owner_steamid64 = 0 WHERE owner_steamid64 IS NULL")
    op.execute(
        "UPDATE server_globalapi SET approved_by_steamid64 = 0 "
        "WHERE approved_by_steamid64 IS NULL"
    )
    op.alter_column(
        "server_globalapi",
        "owner_steamid64",
        existing_type=sa.BigInteger(),
        nullable=False,
    )
    op.alter_column(
        "server_globalapi",
        "approved_by_steamid64",
        existing_type=sa.BigInteger(),
        nullable=False,
    )

    op.create_foreign_key(
        "player_like_viewer_steamid64_fkey",
        "player_like",
        "user",
        ["viewer_steamid64"],
        ["steamid64"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "playerprofileview_viewer_steamid64_fkey",
        "player_profile_view",
        "user",
        ["viewer_steamid64"],
        ["steamid64"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "player_follow_follower_steamid64_fkey",
        "player_follow",
        "user",
        ["follower_steamid64"],
        ["steamid64"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "record_moderation_action_actor_steamid64_fkey",
        "record_moderation_action",
        "user",
        ["actor_steamid64"],
        ["steamid64"],
    )
    op.create_foreign_key(
        "fk_server_group_owner_steamid64_user",
        "server_group",
        "user",
        ["owner_steamid64"],
        ["steamid64"],
    )
    op.create_foreign_key(
        "player_webhook_user_steamid64_fkey",
        "player_webhook",
        "user",
        ["user_steamid64"],
        ["steamid64"],
        ondelete="CASCADE",
    )
