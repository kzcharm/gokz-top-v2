"""add player webhooks

Revision ID: 648051556ea6
Revises: 31c454d04dca
Create Date: 2026-05-07 18:05:16.930460

"""

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = "648051556ea6"
down_revision = "31c454d04dca"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "player_webhook",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_steamid64", sa.BigInteger(), nullable=False),
        sa.Column(
            "provider",
            sa.Enum("discord", name="player_webhook_provider"),
            server_default=sa.text("'discord'"),
            nullable=False,
        ),
        sa.Column("url", sqlmodel.sql.sqltypes.AutoString(length=500), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_steamid64"],
            ["user.steamid64"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_player_webhook_owner_enabled",
        "player_webhook",
        ["user_steamid64", "enabled"],
        unique=False,
    )
    op.create_index(
        "ux_player_webhook_owner_provider_url",
        "player_webhook",
        ["user_steamid64", "provider", "url"],
        unique=True,
    )


def downgrade():
    op.drop_index("ux_player_webhook_owner_provider_url", table_name="player_webhook")
    op.drop_index("ix_player_webhook_owner_enabled", table_name="player_webhook")
    op.drop_table("player_webhook")
    sa.Enum(name="player_webhook_provider").drop(op.get_bind(), checkfirst=True)
