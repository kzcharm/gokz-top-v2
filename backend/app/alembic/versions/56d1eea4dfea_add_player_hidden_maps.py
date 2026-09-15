"""add player hidden maps

Revision ID: 56d1eea4dfea
Revises: 4b80c2f7a91e
Create Date: 2026-09-15 12:10:06.886918

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "56d1eea4dfea"
down_revision = "4b80c2f7a91e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "player_hidden_map",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("player_steamid64", sa.BigInteger(), nullable=False),
        sa.Column("map_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["map_id"], ["map.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["player_steamid64"], ["player.steamid64"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ux_player_hidden_map_player_map",
        "player_hidden_map",
        ["player_steamid64", "map_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ux_player_hidden_map_player_map", table_name="player_hidden_map")
    op.drop_table("player_hidden_map")
