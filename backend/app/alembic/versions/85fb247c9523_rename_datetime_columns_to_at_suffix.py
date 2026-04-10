"""rename datetime columns to at suffix

Revision ID: 85fb247c9523
Revises: 75dd17fdef5e
Create Date: 2026-04-10 17:39:23.680643

"""

from alembic import op
import sqlalchemy as sa


revision = "85fb247c9523"
down_revision = "75dd17fdef5e"
branch_labels = None
depends_on = None


def _rename_column(table_name: str, old_name: str, new_name: str) -> None:
    op.alter_column(table_name, old_name, new_column_name=new_name)


def _rename_index(old_name: str, new_name: str) -> None:
    op.execute(sa.text(f'ALTER INDEX "{old_name}" RENAME TO "{new_name}"'))


def upgrade() -> None:
    _rename_column("ban", "created_on", "created_at")
    _rename_column("ban", "updated_on", "updated_at")
    _rename_index("ix_ban_created_on", "ix_ban_created_at")
    _rename_index("ix_ban_updated_on", "ix_ban_updated_at")

    _rename_column("leaderboard_player", "updated_on", "updated_at")
    _rename_column("leaderboard_player_count", "updated_on", "updated_at")

    _rename_column("map", "created_on", "created_at")
    _rename_column("map", "updated_on", "updated_at")
    _rename_index("ix_map_created_on", "ix_map_created_at")
    _rename_index("ix_map_updated_on", "ix_map_updated_at")

    _rename_column("mode", "created_on", "created_at")
    _rename_column("mode", "updated_on", "updated_at")

    _rename_column("record", "created_on", "created_at")
    _rename_column("record", "updated_on", "updated_at")
    _rename_index("ix_records_created_on_order", "ix_records_created_at_order")
    _rename_index("ix_records_is_valid_created_on", "ix_records_is_valid_created_at")
    _rename_index("ix_records_is_valid_updated_on", "ix_records_is_valid_updated_at")

    _rename_column("record_filter", "created_on", "created_at")
    _rename_column("record_filter", "updated_on", "updated_at")

    _rename_column("record_pb", "updated_on", "updated_at")

    _rename_column("server_globalapi", "created_on", "created_at")
    _rename_column("server_globalapi", "updated_on", "updated_at")


def downgrade() -> None:
    _rename_column("server_globalapi", "updated_at", "updated_on")
    _rename_column("server_globalapi", "created_at", "created_on")

    _rename_column("record_pb", "updated_at", "updated_on")

    _rename_column("record_filter", "updated_at", "updated_on")
    _rename_column("record_filter", "created_at", "created_on")

    _rename_index("ix_records_is_valid_updated_at", "ix_records_is_valid_updated_on")
    _rename_index("ix_records_is_valid_created_at", "ix_records_is_valid_created_on")
    _rename_index("ix_records_created_at_order", "ix_records_created_on_order")
    _rename_column("record", "updated_at", "updated_on")
    _rename_column("record", "created_at", "created_on")

    _rename_column("mode", "updated_at", "updated_on")
    _rename_column("mode", "created_at", "created_on")

    _rename_index("ix_map_updated_at", "ix_map_updated_on")
    _rename_index("ix_map_created_at", "ix_map_created_on")
    _rename_column("map", "updated_at", "updated_on")
    _rename_column("map", "created_at", "created_on")

    _rename_column("leaderboard_player_count", "updated_at", "updated_on")
    _rename_column("leaderboard_player", "updated_at", "updated_on")

    _rename_index("ix_ban_updated_at", "ix_ban_updated_on")
    _rename_index("ix_ban_created_at", "ix_ban_created_on")
    _rename_column("ban", "updated_at", "updated_on")
    _rename_column("ban", "created_at", "created_on")
