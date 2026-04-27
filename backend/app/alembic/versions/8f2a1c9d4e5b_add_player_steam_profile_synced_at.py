"""Add player Steam profile sync timestamp

Revision ID: 8f2a1c9d4e5b
Revises: a9e8d7c6b5a4
Create Date: 2026-04-27 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "8f2a1c9d4e5b"
down_revision = "a9e8d7c6b5a4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "player",
        sa.Column("steam_profile_synced_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_column("player", "steam_profile_synced_at")
