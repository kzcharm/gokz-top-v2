"""add leaderboard player read model

Revision ID: b9c0461664a5
Revises: 2467d30861e8
Create Date: 2026-04-04 19:02:52.447409

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "b9c0461664a5"
down_revision = "2467d30861e8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "leaderboard_player",
        sa.Column("scope", sa.SmallInteger(), nullable=False),
        sa.Column("steamid64", sa.BigInteger(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("rating_easy", sa.Integer(), nullable=False),
        sa.Column("rating_hard", sa.Integer(), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("wrs_nub", sa.Integer(), nullable=False),
        sa.Column("wrs_pro", sa.Integer(), nullable=False),
        sa.Column("records_900_plus", sa.Integer(), nullable=False),
        sa.Column("records_800_plus", sa.Integer(), nullable=False),
        sa.Column("unique_map_finishes", sa.Integer(), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["steamid64"], ["player.steamid64"]),
        sa.PrimaryKeyConstraint("scope", "steamid64"),
    )
    op.create_index(
        "ix_lb_player_scope_rating_pos",
        "leaderboard_player",
        ["scope", sa.literal_column("rating DESC"), "steamid64"],
        unique=False,
        postgresql_where=sa.text("rating > 0"),
    )
    op.create_index(
        "ix_lb_player_scope_rating_easy_pos",
        "leaderboard_player",
        ["scope", sa.literal_column("rating_easy DESC"), "steamid64"],
        unique=False,
        postgresql_where=sa.text("rating_easy > 0"),
    )
    op.create_index(
        "ix_lb_player_scope_rating_hard_pos",
        "leaderboard_player",
        ["scope", sa.literal_column("rating_hard DESC"), "steamid64"],
        unique=False,
        postgresql_where=sa.text("rating_hard > 0"),
    )
    op.create_index(
        "ix_lb_player_scope_points_pos",
        "leaderboard_player",
        ["scope", sa.literal_column("points DESC"), "steamid64"],
        unique=False,
        postgresql_where=sa.text("points > 0"),
    )
    op.create_index(
        "ix_lb_player_scope_wrs_nub_pos",
        "leaderboard_player",
        ["scope", sa.literal_column("wrs_nub DESC"), "steamid64"],
        unique=False,
        postgresql_where=sa.text("wrs_nub > 0"),
    )
    op.create_index(
        "ix_lb_player_scope_wrs_pro_pos",
        "leaderboard_player",
        ["scope", sa.literal_column("wrs_pro DESC"), "steamid64"],
        unique=False,
        postgresql_where=sa.text("wrs_pro > 0"),
    )
    op.create_index(
        "ix_lb_player_scope_900_pos",
        "leaderboard_player",
        ["scope", sa.literal_column("records_900_plus DESC"), "steamid64"],
        unique=False,
        postgresql_where=sa.text("records_900_plus > 0"),
    )
    op.create_index(
        "ix_lb_player_scope_800_pos",
        "leaderboard_player",
        ["scope", sa.literal_column("records_800_plus DESC"), "steamid64"],
        unique=False,
        postgresql_where=sa.text("records_800_plus > 0"),
    )
    op.create_index(
        "ix_lb_player_scope_unique_maps_pos",
        "leaderboard_player",
        ["scope", sa.literal_column("unique_map_finishes DESC"), "steamid64"],
        unique=False,
        postgresql_where=sa.text("unique_map_finishes > 0"),
    )


def downgrade() -> None:
    op.drop_index("ix_lb_player_scope_unique_maps_pos", table_name="leaderboard_player")
    op.drop_index("ix_lb_player_scope_800_pos", table_name="leaderboard_player")
    op.drop_index("ix_lb_player_scope_900_pos", table_name="leaderboard_player")
    op.drop_index("ix_lb_player_scope_wrs_pro_pos", table_name="leaderboard_player")
    op.drop_index("ix_lb_player_scope_wrs_nub_pos", table_name="leaderboard_player")
    op.drop_index("ix_lb_player_scope_points_pos", table_name="leaderboard_player")
    op.drop_index("ix_lb_player_scope_rating_hard_pos", table_name="leaderboard_player")
    op.drop_index("ix_lb_player_scope_rating_easy_pos", table_name="leaderboard_player")
    op.drop_index("ix_lb_player_scope_rating_pos", table_name="leaderboard_player")
    op.drop_table("leaderboard_player")
