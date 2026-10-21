"""index valid records by map course and cutoff time

Revision ID: 13b28094a10e
Revises: 4dfaf2ac4f75
Create Date: 2026-10-22 00:20:46.226994

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "13b28094a10e"
down_revision = "4dfaf2ac4f75"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Build without blocking record submissions on large production tables.
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_record_valid_map_stage_time_uuid",
            "record",
            ["map_id", "stage", "time", "uuid"],
            unique=False,
            postgresql_where=sa.text("is_valid = true"),
            postgresql_concurrently=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(
            "ix_record_valid_map_stage_time_uuid",
            table_name="record",
            postgresql_concurrently=True,
        )
