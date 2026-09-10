"""add workshop preview url cache

Revision ID: a3b7d9e2f104
Revises: 9f2a6c8d1e40
"""

import sqlalchemy as sa
from alembic import op

revision = "a3b7d9e2f104"
down_revision = "9f2a6c8d1e40"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS cache")
    op.create_table(
        "workshop_preview_urls",
        sa.Column("workshop_id", sa.BigInteger(), nullable=False),
        sa.Column("preview_url", sa.String(length=1000), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_attempted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("workshop_id"),
        schema="cache",
    )


def downgrade() -> None:
    op.drop_table("workshop_preview_urls", schema="cache")
