"""add player country lock

Revision ID: 0281971b99a4
Revises: 696d47913104
Create Date: 2026-04-07 11:53:55.837912

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0281971b99a4"
down_revision = "696d47913104"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "player",
        sa.Column(
            "is_country_locked",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.alter_column("player", "is_country_locked", server_default=None)


def downgrade() -> None:
    op.drop_column("player", "is_country_locked")
