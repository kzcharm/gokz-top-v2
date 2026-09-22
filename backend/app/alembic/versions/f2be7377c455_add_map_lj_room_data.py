"""add map lj room data

Revision ID: f2be7377c455
Revises: 11736cf26493
Create Date: 2026-09-22 12:35:22.337570

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f2be7377c455"
down_revision = "11736cf26493"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "map_lj_room",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["id"], ["map.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("map_lj_room")
