"""add player profile history

Revision ID: ff30bfc27fd2
Revises: 487496e5e65a
Create Date: 2026-05-15 16:50:10.543537

"""

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op

# revision identifiers, used by Alembic.
revision = "ff30bfc27fd2"
down_revision = "487496e5e65a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "player_profile_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("player_steamid64", sa.BigInteger(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True),
        sa.Column(
            "avatar_hash", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True
        ),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "name IS NOT NULL OR avatar_hash IS NOT NULL",
            name="ck_player_profile_history_name_or_avatar_present",
        ),
        sa.ForeignKeyConstraint(
            ["player_steamid64"],
            ["player.steamid64"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_player_profile_history_player_steamid64_changed_at",
        "player_profile_history",
        ["player_steamid64", "changed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_player_profile_history_player_steamid64_changed_at",
        table_name="player_profile_history",
    )
    op.drop_table("player_profile_history")
