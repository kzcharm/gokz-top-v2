"""repair player Steam profile sync timestamp column

Revision ID: 5b8d6a7c9e10
Revises: 23ecb026f1dd
Create Date: 2026-04-28 00:00:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "5b8d6a7c9e10"
down_revision = "23ecb026f1dd"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE player
        ADD COLUMN IF NOT EXISTS steam_profile_synced_at TIMESTAMP WITH TIME ZONE
        """
    )


def downgrade() -> None:
    pass
