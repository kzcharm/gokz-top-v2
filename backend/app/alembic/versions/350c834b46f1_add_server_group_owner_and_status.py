"""add server group owner and status

Revision ID: 350c834b46f1
Revises: b8abdacb33ee
Create Date: 2026-04-08 17:20:25.588511

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "350c834b46f1"
down_revision = "b8abdacb33ee"
branch_labels = None
depends_on = None


server_group_status = sa.Enum(
    "pending",
    "validated",
    "invalidated",
    name="server_group_status",
)


def upgrade() -> None:
    server_group_status.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "server_group",
        sa.Column("owner_steamid64", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "server_group",
        sa.Column("status", server_group_status, nullable=True),
    )
    op.execute("UPDATE server_group SET status = 'validated' WHERE status IS NULL")
    op.alter_column("server_group", "status", nullable=False)
    op.create_foreign_key(
        "fk_server_group_owner_steamid64_user",
        "server_group",
        "user",
        ["owner_steamid64"],
        ["steamid64"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_server_group_owner_steamid64_user",
        "server_group",
        type_="foreignkey",
    )
    op.drop_column("server_group", "status")
    op.drop_column("server_group", "owner_steamid64")
    server_group_status.drop(op.get_bind(), checkfirst=True)
