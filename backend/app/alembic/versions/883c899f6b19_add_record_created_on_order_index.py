"""add record created_on order index

Revision ID: 883c899f6b19
Revises: fceabf6eecdf
Create Date: 2026-03-31 17:01:09.132214

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "883c899f6b19"
down_revision = "fceabf6eecdf"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_records_created_on_order",
        "record",
        [
            sa.literal_column("created_on DESC"),
            sa.literal_column("id DESC NULLS LAST"),
            sa.literal_column("uuid DESC"),
        ],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_records_created_on_order", table_name="record")
