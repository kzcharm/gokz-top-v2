"""add record pb updated_at desc index

Revision ID: 11d5fd5344a3
Revises: 85fb247c9523
Create Date: 2026-04-10 17:55:08.049113

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "11d5fd5344a3"
down_revision = "85fb247c9523"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_record_pb_updated_at_desc",
        "record_pb",
        [sa.text("updated_at DESC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_record_pb_updated_at_desc", table_name="record_pb")
