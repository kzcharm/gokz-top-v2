"""add player favorite server

Revision ID: 98c0e0a1a14e
Revises: 8a6d1f0e7c3b
Create Date: 2026-06-08 11:00:48.800048

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "98c0e0a1a14e"
down_revision = "8a6d1f0e7c3b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE player_action ADD VALUE IF NOT EXISTS "
        "'favorite_server_manual_override'"
    )
    op.add_column("player", sa.Column("favorite_server_id", sa.Integer(), nullable=True))
    op.add_column(
        "player",
        sa.Column("favorite_server_group_id", sa.Uuid(), nullable=True),
    )
    op.create_check_constraint(
        "ck_player_favorite_server_single_target",
        "player",
        "favorite_server_id IS NULL OR favorite_server_group_id IS NULL",
    )
    op.create_index(
        "ix_player_favorite_server_group_id",
        "player",
        ["favorite_server_group_id"],
        unique=False,
    )
    op.create_index(
        "ix_player_favorite_server_id",
        "player",
        ["favorite_server_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_player_favorite_server_group_id_server_group",
        "player",
        "server_group",
        ["favorite_server_group_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_player_favorite_server_id_server_globalapi",
        "player",
        "server_globalapi",
        ["favorite_server_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_player_favorite_server_id_server_globalapi",
        "player",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_player_favorite_server_group_id_server_group",
        "player",
        type_="foreignkey",
    )
    op.drop_index("ix_player_favorite_server_id", table_name="player")
    op.drop_index("ix_player_favorite_server_group_id", table_name="player")
    op.drop_constraint(
        "ck_player_favorite_server_single_target",
        "player",
        type_="check",
    )
    op.drop_column("player", "favorite_server_group_id")
    op.drop_column("player", "favorite_server_id")
    # PostgreSQL enums cannot drop individual values without recreating the type.
