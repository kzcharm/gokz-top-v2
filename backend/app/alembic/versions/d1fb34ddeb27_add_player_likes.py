"""add player likes

Revision ID: d1fb34ddeb27
Revises: 3cb64cc3c5c6
Create Date: 2026-05-25 11:26:05.577471

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d1fb34ddeb27"
down_revision = "3cb64cc3c5c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "player_like",
        sa.Column("viewer_steamid64", sa.BigInteger(), nullable=False),
        sa.Column("target_steamid64", sa.BigInteger(), nullable=False),
        sa.Column("like_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["target_steamid64"],
            ["player.steamid64"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["viewer_steamid64"],
            ["user.steamid64"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "viewer_steamid64",
            "target_steamid64",
            "like_date",
        ),
    )
    op.create_index(
        "ix_player_like_target_like_date",
        "player_like",
        ["target_steamid64", "like_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_player_like_target_like_date", table_name="player_like")
    op.drop_table("player_like")
