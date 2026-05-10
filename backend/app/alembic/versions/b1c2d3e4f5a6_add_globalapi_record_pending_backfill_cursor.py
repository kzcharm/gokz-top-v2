"""add globalapi record pending backfill cursor

Revision ID: b1c2d3e4f5a6
Revises: 648051556ea6
Create Date: 2026-05-10 09:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "b1c2d3e4f5a6"
down_revision = "648051556ea6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "globalapi_sync_state",
        sa.Column("pending_backfill_cursor", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("globalapi_sync_state", "pending_backfill_cursor")
