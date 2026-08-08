"""add server global status snapshot

Revision ID: a1b2c3d4e5f6
Revises: 9f4c02fd78c2
Create Date: 2026-08-08 00:00:00.000000

"""

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "a1b2c3d4e5f6"
down_revision = "9f4c02fd78c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "server_live_status",
        sa.Column(
            "global_status",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("server_live_status", "global_status")
