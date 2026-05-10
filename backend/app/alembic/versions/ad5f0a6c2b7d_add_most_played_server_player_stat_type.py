"""add most played server player stat type

Revision ID: ad5f0a6c2b7d
Revises: b1c2d3e4f5a6
Create Date: 2026-05-10 00:00:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "ad5f0a6c2b7d"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE player_stat_type ADD VALUE IF NOT EXISTS 'most_played_server'"
    )


def downgrade() -> None:
    # PostgreSQL enums cannot drop individual values without recreating the type.
    pass
