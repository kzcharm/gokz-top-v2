"""add jumpstat visualization data

Revision ID: 076eccda93e3
Revises: 2e2f1828273f
Create Date: 2026-05-17 14:27:28.853063

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "076eccda93e3"
down_revision = "2e2f1828273f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "jumpstat",
        sa.Column(
            "visualization_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("jumpstat", "visualization_data")
