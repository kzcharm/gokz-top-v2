"""soft delete polls

Revision ID: 9f2a6c8d1e40
Revises: 8e1c4d7a9b20
"""

import sqlalchemy as sa
from alembic import op

revision = "9f2a6c8d1e40"
down_revision = "8e1c4d7a9b20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "poll", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index("ix_poll_deleted_at", "poll", ["deleted_at"])


def downgrade() -> None:
    op.drop_index("ix_poll_deleted_at", table_name="poll")
    op.drop_column("poll", "deleted_at")
