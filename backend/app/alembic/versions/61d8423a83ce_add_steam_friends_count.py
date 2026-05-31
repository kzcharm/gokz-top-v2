"""add steam friends count

Revision ID: 61d8423a83ce
Revises: 7a5fcd7a97f3
Create Date: 2026-05-31 18:02:04.495820

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "61d8423a83ce"
down_revision = "7a5fcd7a97f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "player",
        sa.Column("steam_friends_count", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("player", "steam_friends_count")
