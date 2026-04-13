"""add playtime player stat type

Revision ID: e1a2c3f4b5d6
Revises: efb5342a800e
Create Date: 2026-04-13 22:10:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "e1a2c3f4b5d6"
down_revision = "efb5342a800e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE player_stat_type ADD VALUE IF NOT EXISTS 'playtime'")


def downgrade() -> None:
    # PostgreSQL enums cannot drop individual values without recreating the type.
    pass
