"""add map leaderboard cache

Revision ID: bc1942f54b46
Revises: 5dd433939640
Create Date: 2026-04-15 22:46:05.170679

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "bc1942f54b46"
down_revision = "5dd433939640"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "map_leaderboard",
        sa.Column("map_id", sa.Integer(), nullable=False),
        sa.Column(
            "scope",
            postgresql.ENUM(
                "OVR",
                "KZT",
                "SKZ",
                "VNL",
                name="mode_scope",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("unique_player_finishes", sa.Integer(), nullable=False),
        sa.Column("total_finishes", sa.Integer(), nullable=False),
        sa.Column("total_playtime", sa.Float(), nullable=False),
        sa.Column("average_playtime_per_player", sa.Float(), nullable=False),
        sa.Column("average_finishes_per_player", sa.Float(), nullable=False),
        sa.Column("unique_pro_finishes", sa.Integer(), nullable=False),
        sa.Column("unique_nub_finishes", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["map_id"], ["map.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("map_id", "scope"),
        schema="cache",
    )


def downgrade() -> None:
    op.drop_table("map_leaderboard", schema="cache")
