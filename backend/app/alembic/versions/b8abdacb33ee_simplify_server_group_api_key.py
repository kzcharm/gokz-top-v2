"""simplify server group api key

Revision ID: b8abdacb33ee
Revises: fa468c4f38e7
Create Date: 2026-04-08 16:44:55.777471

"""

import sqlalchemy as sa
from alembic import op

from app.core.security import get_password_hash

# revision identifiers, used by Alembic.
revision = "b8abdacb33ee"
down_revision = "fa468c4f38e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.add_column("server_group", sa.Column("api_key", sa.String(length=36), nullable=True))
    op.execute(
        'UPDATE server_group SET api_key = uuid_generate_v4()::text WHERE api_key IS NULL'
    )
    op.alter_column("server_group", "api_key", nullable=False)
    op.create_index("uq_server_group_api_key", "server_group", ["api_key"], unique=True)
    op.drop_column("server_group", "api_key_created_at")
    op.drop_column("server_group", "api_key_prefix")
    op.drop_column("server_group", "api_key_hash")


def downgrade() -> None:
    op.add_column(
        "server_group",
        sa.Column("api_key_hash", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "server_group",
        sa.Column("api_key_prefix", sa.String(length=12), nullable=True),
    )
    op.add_column(
        "server_group",
        sa.Column("api_key_created_at", sa.DateTime(timezone=True), nullable=True),
    )

    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, api_key FROM server_group")
    ).mappings()
    for row in rows:
        connection.execute(
            sa.text(
                """
                UPDATE server_group
                SET api_key_hash = :api_key_hash,
                    api_key_prefix = :api_key_prefix,
                    api_key_created_at = CURRENT_TIMESTAMP
                WHERE id = :group_id
                """
            ),
            {
                "group_id": row["id"],
                "api_key_hash": get_password_hash(row["api_key"]),
                "api_key_prefix": row["api_key"][:12],
            },
        )

    op.alter_column("server_group", "api_key_hash", nullable=False)
    op.alter_column("server_group", "api_key_prefix", nullable=False)
    op.alter_column("server_group", "api_key_created_at", nullable=False)
    op.drop_index("uq_server_group_api_key", table_name="server_group")
    op.drop_column("server_group", "api_key")
