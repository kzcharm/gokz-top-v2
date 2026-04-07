"""add ban table and globalapi bans mirror

Revision ID: dde2b02a20af
Revises: 0281971b99a4
Create Date: 2026-04-07 12:46:17.981492

"""

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "dde2b02a20af"
down_revision = "0281971b99a4"
branch_labels = None
depends_on = None


ban_type_enum = postgresql.ENUM(
    "ban_evasion",
    "bhop_hack",
    "bhop_macro",
    "exploiting",
    "strafe_hack",
    "strafe_macro",
    "other",
    name="ban_type",
)
ban_type_enum_column = postgresql.ENUM(
    "ban_evasion",
    "bhop_hack",
    "bhop_macro",
    "exploiting",
    "strafe_hack",
    "strafe_macro",
    "other",
    name="ban_type",
    create_type=False,
)


def upgrade() -> None:
    ban_type_enum.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "ban",
        sa.Column("ban_type", ban_type_enum_column, nullable=False),
        sa.Column("expires_on", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True),
        sa.Column("steamid64", sa.BigInteger(), nullable=False),
        sa.Column(
            "player_name",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=True,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("stats", sa.Text(), nullable=True),
        sa.Column("server_id", sa.Integer(), nullable=True),
        sa.Column(
            "updated_by_id",
            sqlmodel.sql.sqltypes.AutoString(length=32),
            nullable=True,
        ),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ban_ban_type", "ban", ["ban_type"], unique=False)
    op.create_index("ix_ban_created_on", "ban", ["created_on"], unique=False)
    op.create_index("ix_ban_server_id", "ban", ["server_id"], unique=False)
    op.create_index(
        "ix_ban_steamid64_expires_on",
        "ban",
        ["steamid64", "expires_on"],
        unique=False,
    )
    op.create_index("ix_ban_updated_on", "ban", ["updated_on"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_ban_updated_on", table_name="ban")
    op.drop_index("ix_ban_steamid64_expires_on", table_name="ban")
    op.drop_index("ix_ban_server_id", table_name="ban")
    op.drop_index("ix_ban_created_on", table_name="ban")
    op.drop_index("ix_ban_ban_type", table_name="ban")
    op.drop_table("ban")
    ban_type_enum.drop(op.get_bind(), checkfirst=True)
