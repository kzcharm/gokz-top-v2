"""v1 style leaderboard sort indexes

Revision ID: dcdbc4fb415d
Revises: 8b7f9f4f9c21
Create Date: 2026-04-10 16:33:51.793434

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "dcdbc4fb415d"
down_revision = "8b7f9f4f9c21"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index(
        op.f("ix_lb_player_scope_800_pos"),
        table_name="leaderboard_player",
        postgresql_where=sa.text("(records_800_plus > 0)"),
    )
    op.drop_index(
        op.f("ix_lb_player_scope_900_pos"),
        table_name="leaderboard_player",
        postgresql_where=sa.text("(records_900_plus > 0)"),
    )
    op.drop_index(
        op.f("ix_lb_player_scope_points_pos"),
        table_name="leaderboard_player",
        postgresql_where=sa.text("(points > 0)"),
    )
    op.drop_index(
        op.f("ix_lb_player_scope_rating_easy_pos"),
        table_name="leaderboard_player",
        postgresql_where=sa.text("(rating_easy > 0)"),
    )
    op.drop_index(
        op.f("ix_lb_player_scope_rating_hard_pos"),
        table_name="leaderboard_player",
        postgresql_where=sa.text("(rating_hard > 0)"),
    )
    op.drop_index(
        op.f("ix_lb_player_scope_rating_pos"),
        table_name="leaderboard_player",
        postgresql_where=sa.text("(rating > 0)"),
    )
    op.drop_index(
        op.f("ix_lb_player_scope_unique_maps_pos"),
        table_name="leaderboard_player",
        postgresql_where=sa.text("(unique_map_finishes > 0)"),
    )
    op.drop_index(
        op.f("ix_lb_player_scope_wrs_nub_pos"),
        table_name="leaderboard_player",
        postgresql_where=sa.text("(wrs_nub > 0)"),
    )
    op.drop_index(
        op.f("ix_lb_player_scope_wrs_pro_pos"),
        table_name="leaderboard_player",
        postgresql_where=sa.text("(wrs_pro > 0)"),
    )

    op.create_index(
        "ix_lb_player_scope_800_order",
        "leaderboard_player",
        [
            "scope",
            sa.literal_column("records_800_plus DESC"),
            sa.literal_column("rating DESC"),
            "steamid64",
        ],
        unique=False,
    )
    op.create_index(
        "ix_lb_player_scope_900_order",
        "leaderboard_player",
        [
            "scope",
            sa.literal_column("records_900_plus DESC"),
            sa.literal_column("rating DESC"),
            "steamid64",
        ],
        unique=False,
    )
    op.create_index(
        "ix_lb_player_scope_points_order",
        "leaderboard_player",
        [
            "scope",
            sa.literal_column("points DESC"),
            sa.literal_column("rating DESC"),
            "steamid64",
        ],
        unique=False,
    )
    op.create_index(
        "ix_lb_player_scope_rating_easy_order",
        "leaderboard_player",
        [
            "scope",
            sa.literal_column("rating_easy DESC"),
            sa.literal_column("rating DESC"),
            "steamid64",
        ],
        unique=False,
    )
    op.create_index(
        "ix_lb_player_scope_rating_hard_order",
        "leaderboard_player",
        [
            "scope",
            sa.literal_column("rating_hard DESC"),
            sa.literal_column("rating DESC"),
            "steamid64",
        ],
        unique=False,
    )
    op.create_index(
        "ix_lb_player_scope_rating_order",
        "leaderboard_player",
        ["scope", sa.literal_column("rating DESC"), "steamid64"],
        unique=False,
    )
    op.create_index(
        "ix_lb_player_scope_unique_maps_order",
        "leaderboard_player",
        [
            "scope",
            sa.literal_column("unique_map_finishes DESC"),
            sa.literal_column("rating DESC"),
            "steamid64",
        ],
        unique=False,
    )
    op.create_index(
        "ix_lb_player_scope_wrs_nub_order",
        "leaderboard_player",
        [
            "scope",
            sa.literal_column("wrs_nub DESC"),
            sa.literal_column("rating DESC"),
            "steamid64",
        ],
        unique=False,
    )
    op.create_index(
        "ix_lb_player_scope_wrs_pro_order",
        "leaderboard_player",
        [
            "scope",
            sa.literal_column("wrs_pro DESC"),
            sa.literal_column("rating DESC"),
            "steamid64",
        ],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_lb_player_scope_wrs_pro_order", table_name="leaderboard_player")
    op.drop_index("ix_lb_player_scope_wrs_nub_order", table_name="leaderboard_player")
    op.drop_index(
        "ix_lb_player_scope_unique_maps_order",
        table_name="leaderboard_player",
    )
    op.drop_index("ix_lb_player_scope_rating_order", table_name="leaderboard_player")
    op.drop_index(
        "ix_lb_player_scope_rating_hard_order",
        table_name="leaderboard_player",
    )
    op.drop_index(
        "ix_lb_player_scope_rating_easy_order",
        table_name="leaderboard_player",
    )
    op.drop_index("ix_lb_player_scope_points_order", table_name="leaderboard_player")
    op.drop_index("ix_lb_player_scope_900_order", table_name="leaderboard_player")
    op.drop_index("ix_lb_player_scope_800_order", table_name="leaderboard_player")

    op.create_index(
        op.f("ix_lb_player_scope_wrs_pro_pos"),
        "leaderboard_player",
        ["scope", sa.literal_column("wrs_pro DESC"), "steamid64"],
        unique=False,
        postgresql_where=sa.text("(wrs_pro > 0)"),
    )
    op.create_index(
        op.f("ix_lb_player_scope_wrs_nub_pos"),
        "leaderboard_player",
        ["scope", sa.literal_column("wrs_nub DESC"), "steamid64"],
        unique=False,
        postgresql_where=sa.text("(wrs_nub > 0)"),
    )
    op.create_index(
        op.f("ix_lb_player_scope_unique_maps_pos"),
        "leaderboard_player",
        ["scope", sa.literal_column("unique_map_finishes DESC"), "steamid64"],
        unique=False,
        postgresql_where=sa.text("(unique_map_finishes > 0)"),
    )
    op.create_index(
        op.f("ix_lb_player_scope_rating_pos"),
        "leaderboard_player",
        ["scope", sa.literal_column("rating DESC"), "steamid64"],
        unique=False,
        postgresql_where=sa.text("(rating > 0)"),
    )
    op.create_index(
        op.f("ix_lb_player_scope_rating_hard_pos"),
        "leaderboard_player",
        ["scope", sa.literal_column("rating_hard DESC"), "steamid64"],
        unique=False,
        postgresql_where=sa.text("(rating_hard > 0)"),
    )
    op.create_index(
        op.f("ix_lb_player_scope_rating_easy_pos"),
        "leaderboard_player",
        ["scope", sa.literal_column("rating_easy DESC"), "steamid64"],
        unique=False,
        postgresql_where=sa.text("(rating_easy > 0)"),
    )
    op.create_index(
        op.f("ix_lb_player_scope_points_pos"),
        "leaderboard_player",
        ["scope", sa.literal_column("points DESC"), "steamid64"],
        unique=False,
        postgresql_where=sa.text("(points > 0)"),
    )
    op.create_index(
        op.f("ix_lb_player_scope_900_pos"),
        "leaderboard_player",
        ["scope", sa.literal_column("records_900_plus DESC"), "steamid64"],
        unique=False,
        postgresql_where=sa.text("(records_900_plus > 0)"),
    )
    op.create_index(
        op.f("ix_lb_player_scope_800_pos"),
        "leaderboard_player",
        ["scope", sa.literal_column("records_800_plus DESC"), "steamid64"],
        unique=False,
        postgresql_where=sa.text("(records_800_plus > 0)"),
    )
