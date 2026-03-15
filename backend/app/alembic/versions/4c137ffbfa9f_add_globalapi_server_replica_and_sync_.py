"""add globalapi server replica and sync state

Revision ID: 4c137ffbfa9f
Revises: c4e58b7407f0
Create Date: 2026-03-15 12:16:10.921387

"""

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes

# revision identifiers, used by Alembic.
revision = "4c137ffbfa9f"
down_revision = "c4e58b7407f0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "globalapi_sync_state",
        sa.Column(
            "task_name",
            sqlmodel.sql.sqltypes.AutoString(length=100),
            nullable=False,
        ),
        sa.Column("last_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_successful_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_processed", sa.Integer(), nullable=False),
        sa.Column("last_created", sa.Integer(), nullable=False),
        sa.Column("last_updated", sa.Integer(), nullable=False),
        sa.Column("last_errors", sa.Integer(), nullable=False),
        sa.Column("last_warnings", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("task_name"),
    )
    op.create_table(
        "server_globalapi",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.Uuid(), nullable=True),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column(
            "ip",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=True,
        ),
        sa.Column(
            "name",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=True,
        ),
        sa.Column("owner_steamid64", sa.BigInteger(), nullable=False),
        sa.Column("approval_status", sa.Integer(), nullable=False),
        sa.Column("approved_by_steamid64", sa.BigInteger(), nullable=False),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["server_group.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_server_globalapi_approval_status",
        "server_globalapi",
        ["approval_status"],
        unique=False,
    )
    op.create_index(
        "ix_server_globalapi_group_id",
        "server_globalapi",
        ["group_id"],
        unique=False,
    )
    op.create_index(
        "ix_server_globalapi_name",
        "server_globalapi",
        ["name"],
        unique=False,
    )
    op.create_index(
        "ix_server_globalapi_owner_steamid64",
        "server_globalapi",
        ["owner_steamid64"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_server_globalapi_owner_steamid64",
        table_name="server_globalapi",
    )
    op.drop_index(
        "ix_server_globalapi_name",
        table_name="server_globalapi",
    )
    op.drop_index(
        "ix_server_globalapi_group_id",
        table_name="server_globalapi",
    )
    op.drop_index(
        "ix_server_globalapi_approval_status",
        table_name="server_globalapi",
    )
    op.drop_table("server_globalapi")
    op.drop_table("globalapi_sync_state")
