"""update server status model

Revision ID: 29703b2b4dc2
Revises: 350c834b46f1
Create Date: 2026-04-08 18:19:49.707711

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "29703b2b4dc2"
down_revision = "350c834b46f1"
branch_labels = None
depends_on = None


server_status_enum = sa.Enum(
    "enabled",
    "invalid",
    "disabled",
    name="server_status",
)
server_source_enum = postgresql.ENUM(
    "manual",
    "steam_master",
    name="server_source",
    create_type=False,
)


def upgrade() -> None:
    server_status_enum.create(op.get_bind(), checkfirst=True)
    op.add_column("server", sa.Column("status", server_status_enum, nullable=True))
    op.execute(
        """
        UPDATE server
        SET status = CASE
            WHEN enabled THEN 'enabled'::server_status
            ELSE 'disabled'::server_status
        END
        """
    )
    op.alter_column("server", "status", nullable=False)

    op.execute(
        """
        ALTER TABLE server
        ALTER COLUMN source TYPE jsonb
        USING CASE
            WHEN source::text = 'steam_master' THEN jsonb_build_object('type', 'steam_master')
            ELSE jsonb_build_object('type', 'manual')
        END
        """
    )

    op.drop_index(op.f("ix_server_enabled"), table_name="server")
    op.create_index("ix_server_status", "server", ["status"], unique=False)

    op.alter_column(
        "server_live_status",
        "current_hostname",
        new_column_name="hostname",
    )
    op.execute(
        """
        UPDATE server_live_status AS sls
        SET hostname = COALESCE(sls.hostname, s.configured_hostname)
        FROM server AS s
        WHERE s.id = sls.server_id
        """
    )

    op.drop_column("server", "configured_hostname")
    op.drop_column("server", "enabled")
    server_source_enum.drop(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    server_source_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "server",
        sa.Column("enabled", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "server",
        sa.Column("configured_hostname", sa.String(length=255), nullable=True),
    )

    op.execute(
        """
        UPDATE server
        SET enabled = (status = 'enabled')
        """
    )
    op.execute(
        """
        UPDATE server AS s
        SET configured_hostname = sls.hostname
        FROM server_live_status AS sls
        WHERE sls.server_id = s.id
        """
    )
    op.alter_column("server", "enabled", nullable=False)

    op.drop_index("ix_server_status", table_name="server")
    op.create_index(op.f("ix_server_enabled"), "server", ["enabled"], unique=False)

    op.execute(
        """
        ALTER TABLE server
        ALTER COLUMN source TYPE server_source
        USING CASE
            WHEN source->>'type' = 'steam_master' THEN 'steam_master'::server_source
            ELSE 'manual'::server_source
        END
        """
    )

    op.drop_column("server", "status")
    server_status_enum.drop(op.get_bind(), checkfirst=True)

    op.alter_column(
        "server_live_status",
        "hostname",
        new_column_name="current_hostname",
    )
