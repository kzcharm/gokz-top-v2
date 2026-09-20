"""classify KZ media posts

Revision ID: 11736cf26493
Revises: 8847d5e6da39
Create Date: 2026-09-20 22:30:20.561653
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "11736cf26493"
down_revision: str | None = "8847d5e6da39"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "media_post",
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "media_post",
        sa.Column(
            "is_kz_video", sa.Boolean(), server_default="false", nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_column("media_post", "is_kz_video")
    op.drop_column("media_post", "tags")
