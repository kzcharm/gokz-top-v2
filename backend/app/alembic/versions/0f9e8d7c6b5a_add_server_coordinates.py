"""add server coordinates

Revision ID: 0f9e8d7c6b5a
Revises: 4f6a8b2c9d10
Create Date: 2026-06-20 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0f9e8d7c6b5a"
down_revision = "4f6a8b2c9d10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("server", sa.Column("latitude", sa.Float(), nullable=True))
    op.add_column("server", sa.Column("longitude", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("server", "longitude")
    op.drop_column("server", "latitude")
