"""add leaderboard player count cache

Revision ID: 75dd17fdef5e
Revises: dcdbc4fb415d
Create Date: 2026-04-10 16:51:36.230279

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "75dd17fdef5e"
down_revision = "dcdbc4fb415d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "leaderboard_player_count",
        sa.Column("scope", sa.SmallInteger(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("scope"),
    )
    op.execute(
        sa.text(
            """
            INSERT INTO leaderboard_player_count (scope, total, updated_on)
            SELECT
                leaderboard_player.scope,
                COUNT(*)::INTEGER,
                NOW()
            FROM leaderboard_player
            GROUP BY leaderboard_player.scope
            """
        )
    )


def downgrade() -> None:
    op.drop_table("leaderboard_player_count")
