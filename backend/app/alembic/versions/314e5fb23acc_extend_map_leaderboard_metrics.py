"""extend map leaderboard metrics

Revision ID: 314e5fb23acc
Revises: bc1942f54b46
Create Date: 2026-04-16 22:39:40.981691

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "314e5fb23acc"
down_revision = "bc1942f54b46"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("map_leaderboard", "unique_player_finishes", schema="cache")
    op.add_column(
        "map_leaderboard",
        sa.Column(
            "average_first_completion_time",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        schema="cache",
    )
    op.add_column(
        "map_leaderboard",
        sa.Column(
            "median_first_completion_time",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        schema="cache",
    )
    op.add_column(
        "map_leaderboard",
        sa.Column(
            "median_playtime_per_player",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        schema="cache",
    )
    op.add_column(
        "map_leaderboard",
        sa.Column(
            "median_finishes_per_player",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        schema="cache",
    )
    op.add_column(
        "map_leaderboard",
        sa.Column(
            "pro_nub_ratio",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        schema="cache",
    )
    op.execute("DELETE FROM cache.map_leaderboard")
    op.alter_column(
        "map_leaderboard",
        "average_first_completion_time",
        server_default=None,
        schema="cache",
    )
    op.alter_column(
        "map_leaderboard",
        "median_first_completion_time",
        server_default=None,
        schema="cache",
    )
    op.alter_column(
        "map_leaderboard",
        "median_playtime_per_player",
        server_default=None,
        schema="cache",
    )
    op.alter_column(
        "map_leaderboard",
        "median_finishes_per_player",
        server_default=None,
        schema="cache",
    )
    op.alter_column(
        "map_leaderboard",
        "pro_nub_ratio",
        server_default=None,
        schema="cache",
    )


def downgrade() -> None:
    op.add_column(
        "map_leaderboard",
        sa.Column(
            "unique_player_finishes",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        schema="cache",
    )
    op.drop_column("map_leaderboard", "pro_nub_ratio", schema="cache")
    op.drop_column("map_leaderboard", "median_finishes_per_player", schema="cache")
    op.drop_column("map_leaderboard", "median_playtime_per_player", schema="cache")
    op.drop_column("map_leaderboard", "median_first_completion_time", schema="cache")
    op.drop_column("map_leaderboard", "average_first_completion_time", schema="cache")
    op.alter_column(
        "map_leaderboard",
        "unique_player_finishes",
        server_default=None,
        schema="cache",
    )
