"""add record steamid64 created_at index

Revision ID: efb5342a800e
Revises: 438918b4fdc5
Create Date: 2026-04-13 17:38:29.881815

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "efb5342a800e"
down_revision = "438918b4fdc5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_records_steamid64_created_at",
        "record",
        ["steamid64", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_records_steamid64_created_at", table_name="record")
