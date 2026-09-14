"""add server public visibility

Revision ID: e823894fb2fd
Revises: 740b0c2cc1d7
Create Date: 2026-09-14 12:15:37.875494

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "e823894fb2fd"
down_revision = "740b0c2cc1d7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "server",
        sa.Column(
            "is_public",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("server", "is_public")
