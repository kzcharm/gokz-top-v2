"""add server group api key last used

Revision ID: c7f2b8a9d1e4
Revises: b2f6c8d9e0a1
Create Date: 2026-05-31 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "c7f2b8a9d1e4"
down_revision = "b2f6c8d9e0a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "server_group",
        sa.Column("last_api_key_used_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("server_group", "last_api_key_used_at")
