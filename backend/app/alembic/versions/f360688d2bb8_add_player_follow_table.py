"""add player follow table

Revision ID: f360688d2bb8
Revises: 50534f197428
Create Date: 2026-04-04 16:01:44.997684

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "f360688d2bb8"
down_revision = "50534f197428"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "player_follow",
        sa.Column("follower_steamid64", sa.BigInteger(), nullable=False),
        sa.Column("followed_steamid64", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "follower_steamid64 != followed_steamid64",
            name="ck_player_follow_not_self",
        ),
        sa.ForeignKeyConstraint(
            ["followed_steamid64"],
            ["player.steamid64"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["follower_steamid64"],
            ["user.steamid64"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("follower_steamid64", "followed_steamid64"),
    )
    op.create_index(
        "ix_player_follow_followed_created_at",
        "player_follow",
        ["followed_steamid64", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_player_follow_follower_created_at",
        "player_follow",
        ["follower_steamid64", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_player_follow_follower_created_at", table_name="player_follow")
    op.drop_index("ix_player_follow_followed_created_at", table_name="player_follow")
    op.drop_table("player_follow")
