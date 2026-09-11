"""add rich server telemetry

Revision ID: 740b0c2cc1d7
Revises: a3b7d9e2f104
Create Date: 2026-09-11 12:29:02.192184

"""

import sqlalchemy as sa
from alembic import op

revision = "740b0c2cc1d7"
down_revision = "a3b7d9e2f104"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "server_live_status",
        sa.Column("sv_ms", sa.Float(), nullable=True),
    )
    op.add_column(
        "server_live_status",
        sa.Column("var_ms", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("server_live_status", "var_ms")
    op.drop_column("server_live_status", "sv_ms")
