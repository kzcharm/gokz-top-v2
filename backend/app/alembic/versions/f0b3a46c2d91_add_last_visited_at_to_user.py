"""Add last_visited_at to User

Revision ID: f0b3a46c2d91
Revises: 9f8c8e2148f1
Create Date: 2026-02-27 23:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f0b3a46c2d91"
down_revision = "9f8c8e2148f1"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "user",
        sa.Column("last_visited_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_column("user", "last_visited_at")
