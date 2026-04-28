"""add player sessions

Revision ID: 23ecb026f1dd
Revises: 8f2a1c9d4e5b
Create Date: 2026-04-28 15:18:04.406638

"""

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "23ecb026f1dd"
down_revision = "8f2a1c9d4e5b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "player_session",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("player_steamid64", sa.BigInteger(), nullable=False),
        sa.Column("server_group_id", sa.Uuid(), nullable=False),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("disconnect_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip_address", postgresql.INET(), nullable=False),
        sa.Column(
            "map_name",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=False,
        ),
        sa.Column(
            "duration_seconds",
            sa.Integer(),
            sa.Computed(
                "EXTRACT(EPOCH FROM (disconnect_at - connected_at))::INTEGER",
                persisted=True,
            ),
            nullable=True,
        ),
        sa.CheckConstraint(
            "disconnect_at IS NULL OR disconnect_at >= connected_at",
            name="ck_player_session_disconnect_after_connect",
        ),
        sa.CheckConstraint(
            "family(ip_address) = 4",
            name="ck_player_session_ipv4",
        ),
        sa.CheckConstraint(
            "last_heartbeat_at >= connected_at",
            name="ck_player_session_heartbeat_after_connect",
        ),
        sa.ForeignKeyConstraint(
            ["player_steamid64"],
            ["player.steamid64"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["server_group_id"],
            ["server_group.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_player_session_group_last_heartbeat_at",
        "player_session",
        ["server_group_id", sa.literal_column("last_heartbeat_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_player_session_group_map_connected_at",
        "player_session",
        ["server_group_id", "map_name", sa.literal_column("connected_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_player_session_ip_connected_at",
        "player_session",
        ["ip_address", sa.literal_column("connected_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_player_session_open_timeout",
        "player_session",
        ["last_heartbeat_at"],
        unique=False,
        postgresql_where=sa.text("disconnect_at IS NULL"),
    )
    op.create_index(
        "ix_player_session_player_connected_at",
        "player_session",
        ["player_steamid64", sa.literal_column("connected_at DESC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_player_session_player_connected_at",
        table_name="player_session",
    )
    op.drop_index(
        "ix_player_session_open_timeout",
        table_name="player_session",
        postgresql_where=sa.text("disconnect_at IS NULL"),
    )
    op.drop_index(
        "ix_player_session_ip_connected_at",
        table_name="player_session",
    )
    op.drop_index(
        "ix_player_session_group_map_connected_at",
        table_name="player_session",
    )
    op.drop_index(
        "ix_player_session_group_last_heartbeat_at",
        table_name="player_session",
    )
    op.drop_table("player_session")
