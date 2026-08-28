"""make pinned records global

Revision ID: 87ad211d8498
Revises: 642a5d19ff8e
Create Date: 2026-08-28 15:12:31.423375

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "87ad211d8498"
down_revision = "642a5d19ff8e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM player_pinned_record AS duplicate
        USING player_pinned_record AS retained
        WHERE duplicate.player_steamid64 = retained.player_steamid64
          AND duplicate.map_id = retained.map_id
          AND duplicate.stage = retained.stage
          AND duplicate.type = retained.type
          AND (duplicate.created_at, duplicate.id) < (retained.created_at, retained.id)
        """
    )
    op.execute(
        """
        DELETE FROM player_pinned_record
        WHERE id IN (
            SELECT id
            FROM (
                SELECT
                    id,
                    row_number() OVER (
                        PARTITION BY player_steamid64
                        ORDER BY created_at DESC, id DESC
                    ) AS pin_rank
                FROM player_pinned_record
            ) AS ranked_pins
            WHERE pin_rank > 6
        )
        """
    )
    op.drop_index(
        "ix_player_pinned_record_player_scope_created_at",
        table_name="player_pinned_record",
    )
    op.drop_index(
        "ux_player_pinned_record_player_map_stage_scope_type",
        table_name="player_pinned_record",
    )
    op.create_index(
        "ix_player_pinned_record_player_created_at",
        "player_pinned_record",
        ["player_steamid64", "created_at"],
    )
    op.create_index(
        "ux_player_pinned_record_player_map_stage_type",
        "player_pinned_record",
        ["player_steamid64", "map_id", "stage", "type"],
        unique=True,
    )
    op.drop_column("player_pinned_record", "scope")


def downgrade() -> None:
    op.add_column(
        "player_pinned_record",
        sa.Column(
            "scope",
            sa.Enum("OVR", "KZT", "SKZ", "VNL", name="mode_scope"),
            server_default="OVR",
            nullable=False,
        ),
    )
    op.drop_index(
        "ux_player_pinned_record_player_map_stage_type",
        table_name="player_pinned_record",
    )
    op.drop_index(
        "ix_player_pinned_record_player_created_at",
        table_name="player_pinned_record",
    )
    op.create_index(
        "ux_player_pinned_record_player_map_stage_scope_type",
        "player_pinned_record",
        ["player_steamid64", "map_id", "stage", "scope", "type"],
        unique=True,
    )
    op.create_index(
        "ix_player_pinned_record_player_scope_created_at",
        "player_pinned_record",
        ["player_steamid64", "scope", "created_at"],
    )
