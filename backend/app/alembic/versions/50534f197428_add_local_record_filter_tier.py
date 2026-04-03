"""add local record filter tier

Revision ID: 50534f197428
Revises: 770aa37ba32f
Create Date: 2026-04-03 16:14:00.730613

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "50534f197428"
down_revision = "770aa37ba32f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("record_filter", sa.Column("tier", sa.Integer(), nullable=True))
    op.execute(
        sa.text(
            """
            UPDATE record_filter
            SET tier = map.difficulty
            FROM map
            WHERE record_filter.map_id = map.id
              AND record_filter.stage = 0
              AND record_filter.tickrate = 128
              AND record_filter.tier IS NULL
            """
        )
    )


def downgrade() -> None:
    op.drop_column("record_filter", "tier")
