"""consolidate server live status state

Revision ID: 6a2f9c4d1b7e
Revises: 29703b2b4dc2
Create Date: 2026-04-08 21:15:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "6a2f9c4d1b7e"
down_revision = "29703b2b4dc2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "server_live_status",
        sa.Column(
            "state",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.execute(
        """
        UPDATE server_live_status
        SET state = jsonb_build_object(
            'last_plugin_seen_at', last_plugin_seen_at,
            'last_a2s_seen_at', last_a2s_seen_at,
            'last_successful_seen_at', last_successful_seen_at,
            'last_valid_seen_at', last_successful_seen_at,
            'invalid_count', 0,
            'timeout_count', 0
        )
        """
    )
    op.alter_column("server_live_status", "state", nullable=False)
    op.drop_index(
        "ix_server_live_status_last_plugin_seen_at",
        table_name="server_live_status",
    )
    op.drop_index(
        "ix_server_live_status_last_a2s_seen_at",
        table_name="server_live_status",
    )
    op.drop_column("server_live_status", "last_successful_seen_at")
    op.drop_column("server_live_status", "last_a2s_seen_at")
    op.drop_column("server_live_status", "last_plugin_seen_at")


def downgrade() -> None:
    op.add_column(
        "server_live_status",
        sa.Column("last_plugin_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "server_live_status",
        sa.Column("last_a2s_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "server_live_status",
        sa.Column("last_successful_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        """
        UPDATE server_live_status
        SET last_plugin_seen_at = (state->>'last_plugin_seen_at')::timestamptz,
            last_a2s_seen_at = (state->>'last_a2s_seen_at')::timestamptz,
            last_successful_seen_at = (state->>'last_successful_seen_at')::timestamptz
        """
    )
    op.create_index(
        "ix_server_live_status_last_plugin_seen_at",
        "server_live_status",
        ["last_plugin_seen_at"],
        unique=False,
    )
    op.create_index(
        "ix_server_live_status_last_a2s_seen_at",
        "server_live_status",
        ["last_a2s_seen_at"],
        unique=False,
    )
    op.drop_column("server_live_status", "state")
