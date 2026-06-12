"""add most played maps player stat type

Revision ID: f7b3c9a1d2e4
Revises: 7b0b365cad40
Create Date: 2026-06-12 00:00:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "f7b3c9a1d2e4"
down_revision = "7b0b365cad40"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE player_stat_type ADD VALUE IF NOT EXISTS 'most_played_maps'")


def downgrade() -> None:
    # PostgreSQL enums cannot drop individual values without recreating the type.
    pass
