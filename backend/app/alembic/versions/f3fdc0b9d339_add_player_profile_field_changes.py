"""add player profile field changes

Revision ID: f3fdc0b9d339
Revises: c1f9a8b7d6e5
Create Date: 2026-05-05 16:50:04.203550

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Connection

# revision identifiers, used by Alembic.
revision = "f3fdc0b9d339"
down_revision = "c1f9a8b7d6e5"
branch_labels = None
depends_on = None

player_profile_field_enum = postgresql.ENUM(
    "alias",
    "custom_id",
    "country",
    name="player_profile_field",
)


def _backfill_country_field_changes(
    connection: Connection,
    *,
    player_table: str = "player",
    field_change_table: str = "player_profile_field_change",
) -> None:
    connection.execute(
        sa.text(
            f"""
            INSERT INTO "{field_change_table}" (
                player_steamid64,
                field,
                changed_at
            )
            SELECT
                steamid64,
                'country'::player_profile_field,
                COALESCE(updated_at, created_at, now())
            FROM "{player_table}"
            WHERE is_country_locked = true
            """
        )
    )


def upgrade() -> None:
    player_profile_field_enum.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "player_profile_field_change",
        sa.Column("player_steamid64", sa.BigInteger(), nullable=False),
        sa.Column(
            "field",
            postgresql.ENUM(
                "alias",
                "custom_id",
                "country",
                name="player_profile_field",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["player_steamid64"],
            ["player.steamid64"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("player_steamid64", "field"),
    )
    _backfill_country_field_changes(op.get_bind())
    op.drop_column("player", "is_country_locked")


def downgrade() -> None:
    op.add_column(
        "player",
        sa.Column(
            "is_country_locked",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.execute(
        """
        UPDATE player
        SET is_country_locked = true
        WHERE EXISTS (
            SELECT 1
            FROM player_profile_field_change
            WHERE player_profile_field_change.player_steamid64 = player.steamid64
              AND player_profile_field_change.field = 'country'::player_profile_field
        )
        """
    )
    op.alter_column("player", "is_country_locked", server_default=None)
    op.drop_table("player_profile_field_change")
    player_profile_field_enum.drop(op.get_bind(), checkfirst=True)
