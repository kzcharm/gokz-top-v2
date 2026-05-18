"""split ban identity for manual bans

Revision ID: bcdbe65cef2b
Revises: e81e547950aa
Create Date: 2026-05-18 12:04:23.410554

"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from secrets import randbits
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Connection

# revision identifiers, used by Alembic.
revision = "bcdbe65cef2b"
down_revision = "e81e547950aa"
branch_labels = None
depends_on = None

_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_BAN_EXTERNAL_ID_INDEX_NAME = "uq_ban_external_id"


def _quoted_identifier(value: str) -> str:
    if not _IDENTIFIER_PATTERN.fullmatch(value):
        raise ValueError(f"Unsafe SQL identifier: {value}")
    return f'"{value}"'


def _normalize_datetime(value: Any) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"Expected datetime, got {type(value)!r}")
    return value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _uuid7_from_timestamp(timestamp: datetime) -> uuid.UUID:
    normalized = _normalize_datetime(timestamp)
    unix_ts_ms = int(normalized.timestamp() * 1000)
    if unix_ts_ms < 0 or unix_ts_ms >= 1 << 48:
        raise ValueError("UUIDv7 timestamp must fit in 48 bits")

    rand_a = randbits(12)
    rand_b = randbits(62)
    value = (
        (unix_ts_ms << 80)
        | (0x7 << 76)
        | (rand_a << 64)
        | (0b10 << 62)
        | rand_b
    )
    return uuid.UUID(int=value)


def _backfill_ban_uuids(
    connection: Connection,
    *,
    ban_table: str = "ban",
) -> None:
    quoted_ban_table = _quoted_identifier(ban_table)
    rows = list(
        connection.execute(
            sa.text(
                f"""
                SELECT id, created_at
                FROM {quoted_ban_table}
                ORDER BY created_at ASC, id ASC
                """
            )
        ).mappings()
    )
    if not rows:
        return

    previous_unix_ts_ms: int | None = None
    updates: list[dict[str, Any]] = []
    for row in rows:
        created_at = _normalize_datetime(row["created_at"])
        unix_ts_ms = int(created_at.timestamp() * 1000)
        if previous_unix_ts_ms is not None and unix_ts_ms <= previous_unix_ts_ms:
            unix_ts_ms = previous_unix_ts_ms + 1

        updates.append(
            {
                "id": row["id"],
                "uuid": _uuid7_from_timestamp(
                    datetime.fromtimestamp(unix_ts_ms / 1000, tz=UTC)
                ),
            }
        )
        previous_unix_ts_ms = unix_ts_ms

    connection.execute(
        sa.text(
            f"""
            UPDATE {quoted_ban_table}
            SET uuid = :uuid
            WHERE id = :id
            """
        ),
        updates,
    )


def _assert_no_manual_bans_without_external_id(
    connection: Connection,
    *,
    ban_table: str = "ban",
) -> None:
    quoted_ban_table = _quoted_identifier(ban_table)
    manual_ban_count = connection.execute(
        sa.text(
            f"""
            SELECT COUNT(*)
            FROM {quoted_ban_table}
            WHERE id IS NULL
            """
        )
    ).scalar_one()
    if manual_ban_count:
        raise RuntimeError(
            "Cannot downgrade while manual bans without GlobalAPI ids exist"
        )


def upgrade() -> None:
    op.add_column(
        "ban",
        sa.Column("uuid", postgresql.UUID(as_uuid=True), nullable=True),
    )
    _backfill_ban_uuids(op.get_bind())
    op.execute(sa.text("ALTER TABLE ban ALTER COLUMN id DROP DEFAULT"))
    op.execute(sa.text("ALTER TABLE ban DROP CONSTRAINT ban_pkey"))
    op.alter_column(
        "ban",
        "uuid",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.create_primary_key("ban_pkey", "ban", ["uuid"])
    op.alter_column(
        "ban",
        "id",
        existing_type=sa.Integer(),
        nullable=True,
    )
    op.create_index(
        _BAN_EXTERNAL_ID_INDEX_NAME,
        "ban",
        ["id"],
        unique=True,
        postgresql_where=sa.text("id IS NOT NULL"),
    )


def downgrade() -> None:
    connection = op.get_bind()
    _assert_no_manual_bans_without_external_id(connection)
    op.drop_index(
        _BAN_EXTERNAL_ID_INDEX_NAME,
        table_name="ban",
        postgresql_where=sa.text("id IS NOT NULL"),
    )
    op.execute(sa.text("ALTER TABLE ban DROP CONSTRAINT ban_pkey"))
    op.alter_column(
        "ban",
        "id",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.create_primary_key("ban_pkey", "ban", ["id"])
    op.execute(
        sa.text(
            """
            ALTER TABLE ban
            ALTER COLUMN id SET DEFAULT nextval('ban_id_seq')
            """
        )
    )
    op.drop_column("ban", "uuid")
