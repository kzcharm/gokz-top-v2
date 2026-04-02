"""add record pb rebuild indexes

Revision ID: 1931535c416e
Revises: b170e1494f90
Create Date: 2026-04-02 20:16:48.907266

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "1931535c416e"
down_revision = "b170e1494f90"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_record_valid_map_stage_mode_player_time",
            "record",
            ["map_id", "stage", "mode_id", "steamid64", "time", "id", "uuid"],
            unique=False,
            postgresql_where=sa.text("is_valid = true"),
            postgresql_concurrently=True,
        )
        op.create_index(
            "ix_record_valid_pro_map_stage_mode_player_time",
            "record",
            ["map_id", "stage", "mode_id", "steamid64", "time", "id", "uuid"],
            unique=False,
            postgresql_where=sa.text("is_valid = true AND teleports = 0"),
            postgresql_concurrently=True,
        )
        op.create_index(
            "ix_record_valid_player_mode_map_stage_time",
            "record",
            ["steamid64", "mode_id", "map_id", "stage", "time", "id", "uuid"],
            unique=False,
            postgresql_where=sa.text("is_valid = true"),
            postgresql_concurrently=True,
        )
        op.create_index(
            "ix_record_valid_pro_player_mode_map_stage_time",
            "record",
            ["steamid64", "mode_id", "map_id", "stage", "time", "id", "uuid"],
            unique=False,
            postgresql_where=sa.text("is_valid = true AND teleports = 0"),
            postgresql_concurrently=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(
            "ix_record_valid_pro_player_mode_map_stage_time",
            table_name="record",
            postgresql_concurrently=True,
        )
        op.drop_index(
            "ix_record_valid_player_mode_map_stage_time",
            table_name="record",
            postgresql_concurrently=True,
        )
        op.drop_index(
            "ix_record_valid_pro_map_stage_mode_player_time",
            table_name="record",
            postgresql_concurrently=True,
        )
        op.drop_index(
            "ix_record_valid_map_stage_mode_player_time",
            table_name="record",
            postgresql_concurrently=True,
        )
