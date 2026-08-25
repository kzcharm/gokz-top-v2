"""add social link visibility preference

Revision ID: 20260825social
Revises: 7b95b12b26e0
Create Date: 2026-08-25
"""

import sqlalchemy as sa
from alembic import op

revision = "20260825social"
down_revision = "7b95b12b26e0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "player_social_link",
        sa.Column("show_on_site", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.alter_column("player_social_link", "show_on_site", server_default=None)


def downgrade() -> None:
    op.drop_column("player_social_link", "show_on_site")
