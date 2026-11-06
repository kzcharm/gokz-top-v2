"""index chronological valid record history

Revision ID: fa7caf33aca5
Revises: cddf87395493
Create Date: 2026-11-06 04:23:26.044934

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "fa7caf33aca5"
down_revision = "cddf87395493"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The record table is large; permit writes throughout the index build.
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_record_valid_map_stage_history",
            "record",
            ["map_id", "stage", "created_at", "id", "uuid"],
            unique=False,
            postgresql_include=["steamid64", "server_id", "mode", "teleports", "time"],
            postgresql_where=sa.text("is_valid = true"),
            postgresql_concurrently=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(
            "ix_record_valid_map_stage_history",
            table_name="record",
            postgresql_concurrently=True,
        )
