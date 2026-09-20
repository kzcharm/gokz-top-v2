"""add skill rating sort indexes

Revision ID: 8847d5e6da39
Revises: ad02b2acec8c
Create Date: 2026-09-20 22:06:51.127154
"""

import sqlalchemy as sa
from alembic import op

revision = "8847d5e6da39"
down_revision = "ad02b2acec8c"
branch_labels = None
depends_on = None

SKILLS = ("boxtech", "strafe", "bhop", "climb", "ladder", "slide")


def upgrade() -> None:
    for skill in SKILLS:
        op.create_index(
            f"ix_lb_player_scope_rating_{skill}_order",
            "leaderboard_player",
            [
                "scope",
                sa.literal_column(f"rating_{skill} DESC"),
                sa.literal_column("rating DESC"),
                "steamid64",
            ],
            unique=False,
        )


def downgrade() -> None:
    for skill in reversed(SKILLS):
        op.drop_index(
            f"ix_lb_player_scope_rating_{skill}_order",
            table_name="leaderboard_player",
        )
