"""Drop map name unique constraint

Revision ID: 6f1dfd8e63b9
Revises: 3a8c1f4e2d10
Create Date: 2026-03-10 00:05:00.000000

"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "6f1dfd8e63b9"
down_revision = "3a8c1f4e2d10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE map DROP CONSTRAINT IF EXISTS uq_map_name")


def downgrade() -> None:
    op.create_unique_constraint("uq_map_name", "map", ["name"])
