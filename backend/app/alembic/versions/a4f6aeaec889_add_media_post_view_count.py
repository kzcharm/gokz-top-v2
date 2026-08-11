"""add media post view count

Revision ID: a4f6aeaec889
Revises: b2c3d4e5f6a7
Create Date: 2026-08-11 16:40:15.247621
"""

import sqlalchemy as sa
from alembic import op

revision = "a4f6aeaec889"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "media_post",
        sa.Column("view_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.alter_column("media_post", "view_count", server_default=None)


def downgrade() -> None:
    op.drop_column("media_post", "view_count")
