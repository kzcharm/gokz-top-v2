"""add server group admin metadata

Revision ID: a9e8d7c6b5a4
Revises: c463639583ad
Create Date: 2026-04-27 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes

# revision identifiers, used by Alembic.
revision = "a9e8d7c6b5a4"
down_revision = "c463639583ad"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "server_group",
        sa.Column(
            "custom_id",
            sqlmodel.sql.sqltypes.AutoString(length=25),
            nullable=True,
        ),
    )
    op.add_column(
        "server_group",
        sa.Column(
            "website",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=True,
        ),
    )
    op.add_column(
        "server_group",
        sa.Column(
            "discord",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=True,
        ),
    )
    op.add_column(
        "server_group",
        sa.Column(
            "steam_group",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=True,
        ),
    )
    op.create_index(
        "uq_server_group_custom_id_not_null",
        "server_group",
        ["custom_id"],
        unique=True,
        postgresql_where=sa.text("custom_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_server_group_custom_id_not_null", table_name="server_group")
    op.drop_column("server_group", "steam_group")
    op.drop_column("server_group", "discord")
    op.drop_column("server_group", "website")
    op.drop_column("server_group", "custom_id")
