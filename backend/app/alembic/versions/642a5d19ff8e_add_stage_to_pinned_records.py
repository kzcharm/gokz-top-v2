"""add stage to pinned records

Revision ID: 642a5d19ff8e
Revises: 20260825social
Create Date: 2026-08-28 14:43:52.489209

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "642a5d19ff8e"
down_revision = "20260825social"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "player_pinned_record",
        sa.Column("stage", sa.Integer(), server_default="0", nullable=False),
    )
    op.drop_index(
        "ux_player_pinned_record_player_map_scope_type",
        table_name="player_pinned_record",
    )
    op.create_index(
        "ux_player_pinned_record_player_map_stage_scope_type",
        "player_pinned_record",
        ["player_steamid64", "map_id", "stage", "scope", "type"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ux_player_pinned_record_player_map_stage_scope_type",
        table_name="player_pinned_record",
    )
    op.create_index(
        "ux_player_pinned_record_player_map_scope_type",
        "player_pinned_record",
        ["player_steamid64", "map_id", "scope", "type"],
        unique=True,
    )
    op.drop_column("player_pinned_record", "stage")
