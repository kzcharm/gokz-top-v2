"""make player report description nullable

Revision ID: 7b8c9d0e1f23
Revises: 2c4d6e8f0a12
Create Date: 2026-06-16 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "7b8c9d0e1f23"
down_revision = "2c4d6e8f0a12"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "player_report",
        "description",
        existing_type=sa.Text(),
        nullable=True,
    )


def downgrade() -> None:
    op.execute("UPDATE player_report SET description = '' WHERE description IS NULL")
    op.alter_column(
        "player_report",
        "description",
        existing_type=sa.Text(),
        nullable=False,
    )
