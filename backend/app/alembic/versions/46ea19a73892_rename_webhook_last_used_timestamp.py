"""rename webhook last used timestamp

Revision ID: 46ea19a73892
Revises: ad5f0a6c2b7d
Create Date: 2026-05-12 16:59:57.614724

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "46ea19a73892"
down_revision = "ad5f0a6c2b7d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    column_names = {
        column["name"] for column in inspector.get_columns("player_webhook")
    }
    if "last_tested_at" in column_names and "last_used_at" not in column_names:
        op.alter_column(
            "player_webhook",
            "last_tested_at",
            new_column_name="last_used_at",
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    column_names = {
        column["name"] for column in inspector.get_columns("player_webhook")
    }
    if "last_used_at" in column_names and "last_tested_at" not in column_names:
        op.alter_column(
            "player_webhook",
            "last_used_at",
            new_column_name="last_tested_at",
        )
