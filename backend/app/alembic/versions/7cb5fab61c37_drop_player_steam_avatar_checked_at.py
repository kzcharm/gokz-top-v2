"""drop player steam avatar checked at

Revision ID: 7cb5fab61c37
Revises: 5b8d6a7c9e10
Create Date: 2026-04-30 11:38:38.627188

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "7cb5fab61c37"
down_revision = "5b8d6a7c9e10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE player
        DROP COLUMN IF EXISTS steam_avatar_checked_at
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE player
        ADD COLUMN IF NOT EXISTS steam_avatar_checked_at TIMESTAMP WITH TIME ZONE
        """
    )
