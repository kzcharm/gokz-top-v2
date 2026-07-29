"""add player steam profile sync attempts

Revision ID: 85e0b395b999
Revises: 0f9e8d7c6b5a
Create Date: 2026-07-29 12:51:29.139668

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "85e0b395b999"
down_revision = "0f9e8d7c6b5a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "player",
        sa.Column("steam_profile_sync_attempted_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_column("player", "steam_profile_sync_attempted_at")
