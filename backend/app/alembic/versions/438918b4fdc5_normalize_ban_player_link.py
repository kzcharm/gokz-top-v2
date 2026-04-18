"""normalize ban player link

Revision ID: 438918b4fdc5
Revises: 517f992fd371
Create Date: 2026-04-13 16:47:59.016609

"""

from __future__ import annotations

import re

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine import Connection

# revision identifiers, used by Alembic.
revision = "438918b4fdc5"
down_revision = "517f992fd371"
branch_labels = None
depends_on = None

_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_BAN_PLAYER_FK_NAME = "fk_ban_steamid64_player"


def _quoted_identifier(value: str) -> str:
    if not _IDENTIFIER_PATTERN.fullmatch(value):
        raise ValueError(f"Unsafe SQL identifier: {value}")
    return f'"{value}"'


def _backfill_players_from_bans(
    connection: Connection,
    *,
    ban_table: str = "ban",
    player_table: str = "player",
) -> None:
    quoted_ban_table = _quoted_identifier(ban_table)
    quoted_player_table = _quoted_identifier(player_table)
    connection.execute(
        sa.text(
            f"""
            INSERT INTO {quoted_player_table} (
                steamid64,
                name,
                is_country_locked,
                created_at,
                last_played_at,
                updated_at
            )
            SELECT
                ban.steamid64,
                COALESCE(
                    MAX(NULLIF(BTRIM(ban.player_name), '')),
                    CAST(ban.steamid64 AS TEXT)
                ) AS name,
                FALSE AS is_country_locked,
                MIN(ban.created_at) AS created_at,
                NULL AS last_played_at,
                CURRENT_TIMESTAMP AS updated_at
            FROM {quoted_ban_table} AS ban
            LEFT JOIN {quoted_player_table} AS player
                ON player.steamid64 = ban.steamid64
            WHERE player.steamid64 IS NULL
            GROUP BY ban.steamid64
            """
        )
    )


def _restore_ban_player_fields(
    connection: Connection,
    *,
    ban_table: str = "ban",
    player_table: str = "player",
) -> None:
    quoted_ban_table = _quoted_identifier(ban_table)
    quoted_player_table = _quoted_identifier(player_table)
    connection.execute(
        sa.text(
            f"""
            UPDATE {quoted_ban_table} AS ban
            SET
                player_name = COALESCE(
                    NULLIF(BTRIM(player.name), ''),
                    CAST(ban.steamid64 AS TEXT)
                ),
                steam_id = CAST(ban.steamid64 AS TEXT)
            FROM {quoted_player_table} AS player
            WHERE player.steamid64 = ban.steamid64
            """
        )
    )
    connection.execute(
        sa.text(
            f"""
            UPDATE {quoted_ban_table}
            SET
                player_name = COALESCE(
                    NULLIF(BTRIM(player_name), ''),
                    CAST(steamid64 AS TEXT)
                ),
                steam_id = COALESCE(steam_id, CAST(steamid64 AS TEXT))
            """
        )
    )


def upgrade() -> None:
    connection = op.get_bind()
    _backfill_players_from_bans(connection)
    op.create_foreign_key(
        _BAN_PLAYER_FK_NAME,
        "ban",
        "player",
        ["steamid64"],
        ["steamid64"],
    )
    op.execute("ALTER TABLE ban DROP COLUMN IF EXISTS steam_id")
    op.execute("ALTER TABLE ban DROP COLUMN IF EXISTS player_name")


def downgrade() -> None:
    connection = op.get_bind()
    op.add_column(
        "ban",
        sa.Column("player_name", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "ban",
        sa.Column("steam_id", sa.String(length=32), nullable=True),
    )
    _restore_ban_player_fields(connection)
    op.drop_constraint(_BAN_PLAYER_FK_NAME, "ban", type_="foreignkey")
