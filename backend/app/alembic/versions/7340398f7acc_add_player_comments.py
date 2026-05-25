"""add player comments

Revision ID: 7340398f7acc
Revises: 3cb64cc3c5c6
Create Date: 2026-05-25 11:20:40.512813

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "7340398f7acc"
down_revision = "3cb64cc3c5c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "player_comment",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("author_steamid64", sa.BigInteger(), nullable=False),
        sa.Column("target_steamid64", sa.BigInteger(), nullable=False),
        sa.Column("text", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["author_steamid64"],
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
        "ix_player_comment_author_created_at_id",
        "player_comment",
        ["author_steamid64", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_player_comment_target_created_at_id",
        "player_comment",
        ["target_steamid64", "created_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_player_comment_target_created_at_id", table_name="player_comment")
    op.drop_index("ix_player_comment_author_created_at_id", table_name="player_comment")
    op.drop_table("player_comment")
