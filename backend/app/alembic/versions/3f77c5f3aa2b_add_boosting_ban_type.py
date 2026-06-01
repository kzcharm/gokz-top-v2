"""add boosting ban type

Revision ID: 3f77c5f3aa2b
Revises: 61d8423a83ce
Create Date: 2026-06-01 00:00:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "3f77c5f3aa2b"
down_revision = "61d8423a83ce"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE ban_type ADD VALUE IF NOT EXISTS 'boosting'")


def downgrade() -> None:
    # PostgreSQL enums cannot drop individual values without recreating the type.
    pass
