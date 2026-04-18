"""enum back mode and scope storage

Revision ID: 79409830f127
Revises: 314e5fb23acc
Create Date: 2026-04-17 21:44:53.212433

"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine import Connection

# revision identifiers, used by Alembic.
revision = "79409830f127"
down_revision = "314e5fb23acc"
branch_labels = None
depends_on = None

LOGGER = logging.getLogger("alembic.runtime.migration")

MODE_ID_TO_KZ_MODE: dict[int, str] = {
    200: "KZT",
    201: "SKZ",
    202: "VNL",
    203: "NKZ",
}
SCOPE_ID_TO_MODE_SCOPE: dict[int, str] = {
    0: "OVR",
    1: "KZT",
    2: "SKZ",
    3: "VNL",
}

RECORD_BATCH_SIZE = 500_000
RECORD_FILTER_BATCH_SIZE = 50_000
RECORD_PB_BATCH_SIZE = 500_000


def _log(message: str, *args: object) -> None:
    LOGGER.info(message, *args)


def _scalar(connection: Connection, sql: str, **params: Any) -> Any:
    return connection.execute(sa.text(sql), params).scalar_one()


def _scalar_or_none(connection: Connection, sql: str, **params: Any) -> Any:
    return connection.execute(sa.text(sql), params).scalar_one_or_none()


def _mapping_row(connection: Connection, sql: str, **params: Any) -> dict[str, Any]:
    return dict(connection.execute(sa.text(sql), params).mappings().one())


def _table_count(connection: Connection, table_name: str) -> int:
    return int(_scalar(connection, f"SELECT COUNT(*) FROM {table_name}"))


def _enum_case_sql(column_sql: str, mapping: Mapping[int, str], enum_type: str) -> str:
    branches = "\n".join(
        f"        WHEN {legacy_value} THEN '{enum_value}'::{enum_type}"
        for legacy_value, enum_value in mapping.items()
    )
    return f"""CASE {column_sql}
{branches}
        ELSE NULL
    END"""


def _get_column_udt_name(
    connection: Connection,
    *,
    table_name: str,
    column_name: str,
) -> str | None:
    return _scalar(
        connection,
        """
        SELECT udt_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = :table_name
          AND column_name = :column_name
        """,
        table_name=table_name,
        column_name=column_name,
    )


def _index_exists(connection: Connection, index_name: str) -> bool:
    return bool(_scalar(connection, "SELECT to_regclass(:index_name) IS NOT NULL", index_name=index_name))


def _constraint_exists(connection: Connection, *, table_name: str, constraint_name: str) -> bool:
    return bool(
        _scalar(
            connection,
            """
            SELECT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conrelid = CAST(:table_name AS regclass)
                  AND conname = :constraint_name
            )
            """,
            table_name=table_name,
            constraint_name=constraint_name,
        )
    )


def _group_counts(
    connection: Connection,
    *,
    table_name: str,
    column_name: str,
) -> dict[Any, int]:
    rows = connection.execute(
        sa.text(
            f"""
            SELECT {column_name} AS value, COUNT(*) AS row_count
            FROM {table_name}
            GROUP BY {column_name}
            ORDER BY {column_name}
            """
        )
    ).all()
    return {value: int(row_count) for value, row_count in rows}


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _assert_no_unmapped_values(connection: Connection) -> None:
    invalid_record_modes = int(
        _scalar(
            connection,
            "SELECT COUNT(*) FROM record WHERE mode_id NOT IN (200, 201, 202, 203)",
        )
    )
    invalid_record_filter_modes = int(
        _scalar(
            connection,
            "SELECT COUNT(*) FROM record_filter WHERE mode_id NOT IN (200, 201, 202, 203)",
        )
    )
    invalid_record_pb_scopes = int(
        _scalar(
            connection,
            "SELECT COUNT(*) FROM record_pb WHERE scope NOT IN (0, 1, 2, 3)",
        )
    )
    _assert(invalid_record_modes == 0, "record has unmapped mode_id values")
    _assert(invalid_record_filter_modes == 0, "record_filter has unmapped mode_id values")
    _assert(invalid_record_pb_scopes == 0, "record_pb has unmapped scope values")


def _assert_shadow_column_state(
    connection: Connection,
    *,
    record_count: int,
    record_filter_count: int,
    record_pb_count: int,
) -> None:
    _assert(
        int(_scalar(connection, "SELECT COUNT(*) FROM record WHERE mode_new IS NULL")) == 0,
        "record.mode_new still contains NULL values",
    )
    _assert(
        int(
            _scalar(
                connection,
                "SELECT COUNT(*) FROM record_filter WHERE mode_new IS NULL",
            )
        )
        == 0,
        "record_filter.mode_new still contains NULL values",
    )
    _assert(
        int(
            _scalar(
                connection,
                "SELECT COUNT(*) FROM record_pb WHERE scope_new IS NULL",
            )
        )
        == 0,
        "record_pb.scope_new still contains NULL values",
    )
    _assert(_table_count(connection, "record") == record_count, "record row count changed")
    _assert(
        _table_count(connection, "record_filter") == record_filter_count,
        "record_filter row count changed",
    )
    _assert(
        _table_count(connection, "record_pb") == record_pb_count,
        "record_pb row count changed",
    )

    expected_record_counts = {
        MODE_ID_TO_KZ_MODE[mode_id]: row_count
        for mode_id, row_count in _group_counts(
            connection,
            table_name="record",
            column_name="mode_id",
        ).items()
    }
    expected_record_filter_counts = {
        MODE_ID_TO_KZ_MODE[mode_id]: row_count
        for mode_id, row_count in _group_counts(
            connection,
            table_name="record_filter",
            column_name="mode_id",
        ).items()
    }
    expected_record_pb_counts = {
        SCOPE_ID_TO_MODE_SCOPE[scope_id]: row_count
        for scope_id, row_count in _group_counts(
            connection,
            table_name="record_pb",
            column_name="scope",
        ).items()
    }

    _assert(
        expected_record_counts
        == _group_counts(connection, table_name="record", column_name="mode_new"),
        "record mode grouped counts do not match backfilled enum counts",
    )
    _assert(
        expected_record_filter_counts
        == _group_counts(connection, table_name="record_filter", column_name="mode_new"),
        "record_filter mode grouped counts do not match backfilled enum counts",
    )
    _assert(
        expected_record_pb_counts
        == _group_counts(connection, table_name="record_pb", column_name="scope_new"),
        "record_pb scope grouped counts do not match backfilled enum counts",
    )


def _assert_post_cutover_state(
    connection: Connection,
    *,
    record_count: int,
    record_filter_count: int,
    record_pb_count: int,
) -> None:
    _assert(_table_count(connection, "record") == record_count, "record row count changed")
    _assert(
        _table_count(connection, "record_filter") == record_filter_count,
        "record_filter row count changed",
    )
    _assert(
        _table_count(connection, "record_pb") == record_pb_count,
        "record_pb row count changed",
    )

    for index_name in (
        "ix_pb_map_nub",
        "ix_pb_map_ovr",
        "ix_pb_map_pro",
        "ix_pb_player_nub",
        "ix_pb_player_ovr",
        "ix_pb_player_pro",
        "ix_record_valid_map_stage_mode_player_time",
        "ix_record_valid_player_mode_map_stage_time",
        "ix_record_valid_pro_map_stage_mode_player_time",
        "ix_record_valid_pro_player_mode_map_stage_time",
        "ix_record_filter_availability",
        "ix_record_filter_lookup",
        "ix_record_pb_scope_course_pro_time_uuid",
        "ix_record_pb_player_scope_pro_course_time",
        "ix_record_pb_record_uuid_scope_pro",
        "ix_record_pb_updated_at_desc",
        "ux_record_pb_wr_scope_course_type",
    ):
        _assert(_index_exists(connection, index_name), f"missing expected index {index_name}")

    _assert(
        _constraint_exists(connection, table_name="record_pb", constraint_name="record_pb_pkey"),
        "record_pb primary key constraint missing after cutover",
    )
    _assert(
        _constraint_exists(connection, table_name="record", constraint_name="record_mode_fkey"),
        "record mode foreign key missing after cutover",
    )
    _assert(
        _constraint_exists(
            connection,
            table_name="record_filter",
            constraint_name="record_filter_mode_fkey",
        ),
        "record_filter mode foreign key missing after cutover",
    )

    compatibility_type = _scalar_or_none(
        connection,
        """
        SELECT pg_typeof(mode_id)::text
        FROM (
            SELECT mode.id AS mode_id
            FROM record
            JOIN mode ON record.mode = mode.name_short
            LIMIT 1
        ) AS compatibility_probe
        """,
    )
    if compatibility_type is not None:
        _assert(
            compatibility_type in {"integer", "int4"},
            "mode compatibility join no longer returns numeric mode_id values",
        )
    duplicate_wr = connection.execute(
        sa.text(
            """
            SELECT scope, course_id, is_pro_only, COUNT(*) AS row_count
            FROM record_pb
            WHERE points = 1000
            GROUP BY scope, course_id, is_pro_only
            HAVING COUNT(*) > 1
            LIMIT 1
            """
        )
    ).first()
    _assert(duplicate_wr is None, "record_pb WR uniqueness no longer holds")


def _ensure_kz_mode_type(connection: Connection) -> None:
    connection.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_type
                    WHERE typname = 'kz_mode'
                ) THEN
                    CREATE TYPE kz_mode AS ENUM ('KZT', 'SKZ', 'VNL', 'NKZ');
                END IF;
            END
            $$;
            """
        )
    )


def _convert_mode_name_short_to_enum(connection: Connection) -> None:
    _assert(
        int(
            _scalar(
                connection,
                """
                SELECT COUNT(*)
                FROM mode
                WHERE name_short NOT IN ('KZT', 'SKZ', 'VNL', 'NKZ')
                """,
            )
        )
        == 0,
        "mode.name_short contains values outside kz_mode",
    )
    if _get_column_udt_name(connection, table_name="mode", column_name="name_short") == "kz_mode":
        return
    connection.execute(
        sa.text(
            """
            ALTER TABLE mode
            ALTER COLUMN name_short TYPE kz_mode
            USING name_short::text::kz_mode
            """
        )
    )


def _add_shadow_columns(connection: Connection) -> None:
    connection.execute(sa.text("ALTER TABLE record ADD COLUMN IF NOT EXISTS mode_new kz_mode"))
    connection.execute(
        sa.text("ALTER TABLE record_filter ADD COLUMN IF NOT EXISTS mode_new kz_mode")
    )
    connection.execute(
        sa.text("ALTER TABLE record_pb ADD COLUMN IF NOT EXISTS scope_new mode_scope")
    )


def _backfill_record_mode(connection: Connection) -> None:
    case_sql = _enum_case_sql("record.mode_id", MODE_ID_TO_KZ_MODE, "kz_mode")
    total_updated = 0
    last_uuid: str | None = None
    batch_number = 0
    while True:
        cursor_filter = ""
        params: dict[str, Any] = {"batch_size": RECORD_BATCH_SIZE}
        if last_uuid is not None:
            cursor_filter = "AND uuid > CAST(:last_uuid AS uuid)"
            params["last_uuid"] = last_uuid
        row = _mapping_row(
            connection,
            f"""
            WITH batch AS (
                SELECT uuid
                FROM record
                WHERE mode_new IS NULL
                  {cursor_filter}
                ORDER BY uuid
                LIMIT :batch_size
            ),
            updated AS (
                UPDATE record
                SET mode_new = {case_sql}
                FROM batch
                WHERE record.uuid = batch.uuid
                RETURNING record.uuid
            )
            SELECT
                COALESCE((SELECT COUNT(*) FROM updated), 0) AS updated_rows,
                (
                    SELECT uuid
                    FROM batch
                    ORDER BY uuid DESC
                    LIMIT 1
                ) AS last_uuid
            """,
            **params,
        )
        updated_rows = int(row["updated_rows"])
        if updated_rows == 0:
            break
        total_updated += updated_rows
        batch_number += 1
        last_uuid = str(row["last_uuid"])
        _log(
            "record.mode_new backfill batch=%s rows=%s total=%s",
            batch_number,
            updated_rows,
            total_updated,
        )


def _backfill_record_filter_mode(connection: Connection) -> None:
    case_sql = _enum_case_sql("record_filter.mode_id", MODE_ID_TO_KZ_MODE, "kz_mode")
    total_updated = 0
    last_id: int | None = None
    batch_number = 0
    while True:
        cursor_filter = ""
        params: dict[str, Any] = {"batch_size": RECORD_FILTER_BATCH_SIZE}
        if last_id is not None:
            cursor_filter = "AND id > CAST(:last_id AS integer)"
            params["last_id"] = last_id
        row = _mapping_row(
            connection,
            f"""
            WITH batch AS (
                SELECT id
                FROM record_filter
                WHERE mode_new IS NULL
                  {cursor_filter}
                ORDER BY id
                LIMIT :batch_size
            ),
            updated AS (
                UPDATE record_filter
                SET mode_new = {case_sql}
                FROM batch
                WHERE record_filter.id = batch.id
                RETURNING record_filter.id
            )
            SELECT
                COALESCE((SELECT COUNT(*) FROM updated), 0) AS updated_rows,
                (SELECT MAX(id) FROM batch) AS last_id
            """,
            **params,
        )
        updated_rows = int(row["updated_rows"])
        if updated_rows == 0:
            break
        total_updated += updated_rows
        batch_number += 1
        last_id = int(row["last_id"])
        _log(
            "record_filter.mode_new backfill batch=%s rows=%s total=%s",
            batch_number,
            updated_rows,
            total_updated,
        )


def _backfill_record_pb_scope(connection: Connection) -> None:
    case_sql = _enum_case_sql("record_pb.scope", SCOPE_ID_TO_MODE_SCOPE, "mode_scope")
    total_updated = 0
    last_scope: int | None = None
    last_course_id: int | None = None
    last_steamid64: int | None = None
    last_is_pro_only: bool | None = None
    batch_number = 0
    while True:
        cursor_filter = ""
        params: dict[str, Any] = {"batch_size": RECORD_PB_BATCH_SIZE}
        if last_scope is not None:
            cursor_filter = """
                  AND (scope, course_id, steamid64, is_pro_only) > (
                        CAST(:last_scope AS smallint),
                        CAST(:last_course_id AS integer),
                        CAST(:last_steamid64 AS bigint),
                        CAST(:last_is_pro_only AS boolean)
                  )
            """
            params.update(
                last_scope=last_scope,
                last_course_id=last_course_id,
                last_steamid64=last_steamid64,
                last_is_pro_only=last_is_pro_only,
            )
        row = _mapping_row(
            connection,
            f"""
            WITH batch AS (
                SELECT scope, course_id, steamid64, is_pro_only
                FROM record_pb
                WHERE scope_new IS NULL
                  {cursor_filter}
                ORDER BY scope, course_id, steamid64, is_pro_only
                LIMIT :batch_size
            ),
            updated AS (
                UPDATE record_pb
                SET scope_new = {case_sql}
                FROM batch
                WHERE record_pb.scope = batch.scope
                  AND record_pb.course_id = batch.course_id
                  AND record_pb.steamid64 = batch.steamid64
                  AND record_pb.is_pro_only = batch.is_pro_only
                RETURNING record_pb.scope
            )
            SELECT
                COALESCE((SELECT COUNT(*) FROM updated), 0) AS updated_rows,
                (
                    SELECT scope
                    FROM batch
                    ORDER BY scope DESC, course_id DESC, steamid64 DESC, is_pro_only DESC
                    LIMIT 1
                ) AS last_scope,
                (
                    SELECT course_id
                    FROM batch
                    ORDER BY scope DESC, course_id DESC, steamid64 DESC, is_pro_only DESC
                    LIMIT 1
                ) AS last_course_id,
                (
                    SELECT steamid64
                    FROM batch
                    ORDER BY scope DESC, course_id DESC, steamid64 DESC, is_pro_only DESC
                    LIMIT 1
                ) AS last_steamid64,
                (
                    SELECT is_pro_only
                    FROM batch
                    ORDER BY scope DESC, course_id DESC, steamid64 DESC, is_pro_only DESC
                    LIMIT 1
                ) AS last_is_pro_only
            """,
            **params,
        )
        updated_rows = int(row["updated_rows"])
        if updated_rows == 0:
            break
        total_updated += updated_rows
        batch_number += 1
        last_scope = int(row["last_scope"])
        last_course_id = int(row["last_course_id"])
        last_steamid64 = int(row["last_steamid64"])
        last_is_pro_only = bool(row["last_is_pro_only"])
        _log(
            "record_pb.scope_new backfill batch=%s rows=%s total=%s",
            batch_number,
            updated_rows,
            total_updated,
        )


def _create_concurrent_indexes(connection: Connection) -> None:
    del connection
    statements = (
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_pb_map_nub_new
        ON record (map_id, stage, steamid64, "time", mode_new)
        WHERE is_valid = true AND teleports > 0
        """,
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_pb_map_ovr_new
        ON record (map_id, stage, steamid64, "time", mode_new)
        WHERE is_valid = true
        """,
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_pb_map_pro_new
        ON record (map_id, stage, steamid64, "time", mode_new)
        WHERE is_valid = true AND teleports = 0
        """,
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_pb_player_nub_new
        ON record (steamid64, map_id, stage, "time", mode_new)
        WHERE is_valid = true AND teleports > 0
        """,
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_pb_player_ovr_new
        ON record (steamid64, map_id, stage, "time", mode_new)
        WHERE is_valid = true
        """,
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_pb_player_pro_new
        ON record (steamid64, map_id, stage, "time", mode_new)
        WHERE is_valid = true AND teleports = 0
        """,
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_record_valid_map_stage_mode_player_time_new
        ON record (map_id, stage, mode_new, steamid64, "time", id, uuid)
        WHERE is_valid = true
        """,
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_record_valid_pro_map_stage_mode_player_time_new
        ON record (map_id, stage, mode_new, steamid64, "time", id, uuid)
        WHERE is_valid = true AND teleports = 0
        """,
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_record_valid_player_mode_map_stage_time_new
        ON record (steamid64, mode_new, map_id, stage, "time", id, uuid)
        WHERE is_valid = true
        """,
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_record_valid_pro_player_mode_map_stage_time_new
        ON record (steamid64, mode_new, map_id, stage, "time", id, uuid)
        WHERE is_valid = true AND teleports = 0
        """,
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_record_filter_availability_new
        ON record_filter (stage, mode_new, map_id, has_teleports, id)
        """,
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_record_filter_lookup_new
        ON record_filter (map_id, stage, mode_new, tickrate, has_teleports, id)
        """,
        """
        CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ux_record_pb_pkey_new
        ON record_pb (scope_new, course_id, steamid64, is_pro_only)
        """,
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_record_pb_scope_course_pro_time_uuid_new
        ON record_pb (scope_new, course_id, is_pro_only, time_ms, record_uuid)
        """,
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_record_pb_player_scope_pro_course_time_new
        ON record_pb (steamid64, scope_new, is_pro_only, course_id, time_ms)
        """,
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_record_pb_record_uuid_scope_pro_new
        ON record_pb (record_uuid, scope_new, is_pro_only)
        """,
        """
        CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ux_record_pb_wr_scope_course_type_new
        ON record_pb (scope_new, course_id, is_pro_only)
        WHERE points = 1000
        """,
    )
    for statement in statements:
        op.execute(statement)


def _add_and_validate_foreign_keys(connection: Connection) -> None:
    missing_mode_refs = int(
        _scalar(
            connection,
            """
            WITH referenced_modes AS (
                SELECT DISTINCT mode_new AS mode
                FROM record
                WHERE mode_new IS NOT NULL
                UNION
                SELECT DISTINCT mode_new AS mode
                FROM record_filter
                WHERE mode_new IS NOT NULL
            )
            SELECT COUNT(*)
            FROM referenced_modes
            LEFT JOIN mode ON referenced_modes.mode = mode.name_short
            WHERE mode.name_short IS NULL
            """,
        )
    )
    _assert(missing_mode_refs == 0, "record or record_filter reference missing mode rows")

    connection.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = 'record_mode_new_fkey'
                      AND conrelid = 'record'::regclass
                ) THEN
                    ALTER TABLE record
                    ADD CONSTRAINT record_mode_new_fkey
                    FOREIGN KEY (mode_new) REFERENCES mode (name_short) NOT VALID;
                END IF;
            END
            $$;
            """
        )
    )
    connection.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = 'record_filter_mode_new_fkey'
                      AND conrelid = 'record_filter'::regclass
                ) THEN
                    ALTER TABLE record_filter
                    ADD CONSTRAINT record_filter_mode_new_fkey
                    FOREIGN KEY (mode_new) REFERENCES mode (name_short) NOT VALID;
                END IF;
            END
            $$;
            """
        )
    )
    connection.execute(sa.text("ALTER TABLE record VALIDATE CONSTRAINT record_mode_new_fkey"))
    connection.execute(
        sa.text("ALTER TABLE record_filter VALIDATE CONSTRAINT record_filter_mode_new_fkey")
    )


def _cutover(connection: Connection) -> None:
    connection.execute(sa.text("ALTER TABLE record_filter ALTER COLUMN mode_new SET NOT NULL"))
    connection.execute(sa.text("ALTER TABLE record ALTER COLUMN mode_new SET NOT NULL"))
    connection.execute(sa.text("ALTER TABLE record_pb ALTER COLUMN scope_new SET NOT NULL"))

    connection.execute(
        sa.text("ALTER TABLE record_filter DROP CONSTRAINT IF EXISTS record_filter_mode_id_fkey")
    )
    connection.execute(sa.text("ALTER TABLE record DROP CONSTRAINT IF EXISTS record_mode_id_fkey"))
    connection.execute(sa.text("ALTER TABLE record_pb DROP CONSTRAINT IF EXISTS record_pb_pkey"))

    connection.execute(
        sa.text("ALTER TABLE record_filter RENAME COLUMN mode_id TO mode_id_old")
    )
    connection.execute(sa.text("ALTER TABLE record_filter RENAME COLUMN mode_new TO mode"))
    connection.execute(sa.text("ALTER TABLE record RENAME COLUMN mode_id TO mode_id_old"))
    connection.execute(sa.text("ALTER TABLE record RENAME COLUMN mode_new TO mode"))
    connection.execute(sa.text("ALTER TABLE record_pb RENAME COLUMN scope TO scope_old"))
    connection.execute(sa.text("ALTER TABLE record_pb RENAME COLUMN scope_new TO scope"))

    connection.execute(sa.text("DROP INDEX IF EXISTS ix_pb_map_nub"))
    connection.execute(sa.text("DROP INDEX IF EXISTS ix_pb_map_ovr"))
    connection.execute(sa.text("DROP INDEX IF EXISTS ix_pb_map_pro"))
    connection.execute(sa.text("DROP INDEX IF EXISTS ix_pb_player_nub"))
    connection.execute(sa.text("DROP INDEX IF EXISTS ix_pb_player_ovr"))
    connection.execute(sa.text("DROP INDEX IF EXISTS ix_pb_player_pro"))
    connection.execute(sa.text("DROP INDEX IF EXISTS ix_record_valid_map_stage_mode_player_time"))
    connection.execute(
        sa.text("DROP INDEX IF EXISTS ix_record_valid_pro_map_stage_mode_player_time")
    )
    connection.execute(sa.text("DROP INDEX IF EXISTS ix_record_valid_player_mode_map_stage_time"))
    connection.execute(
        sa.text("DROP INDEX IF EXISTS ix_record_valid_pro_player_mode_map_stage_time")
    )
    connection.execute(sa.text("DROP INDEX IF EXISTS ix_record_filter_availability"))
    connection.execute(sa.text("DROP INDEX IF EXISTS ix_record_filter_lookup"))
    connection.execute(sa.text("DROP INDEX IF EXISTS ix_record_pb_scope_course_pro_time_uuid"))
    connection.execute(sa.text("DROP INDEX IF EXISTS ix_record_pb_player_scope_pro_course_time"))
    connection.execute(sa.text("DROP INDEX IF EXISTS ix_record_pb_record_uuid_scope_pro"))
    connection.execute(sa.text("DROP INDEX IF EXISTS ux_record_pb_wr_scope_course_type"))

    connection.execute(sa.text("ALTER INDEX ix_pb_map_nub_new RENAME TO ix_pb_map_nub"))
    connection.execute(sa.text("ALTER INDEX ix_pb_map_ovr_new RENAME TO ix_pb_map_ovr"))
    connection.execute(sa.text("ALTER INDEX ix_pb_map_pro_new RENAME TO ix_pb_map_pro"))
    connection.execute(sa.text("ALTER INDEX ix_pb_player_nub_new RENAME TO ix_pb_player_nub"))
    connection.execute(sa.text("ALTER INDEX ix_pb_player_ovr_new RENAME TO ix_pb_player_ovr"))
    connection.execute(sa.text("ALTER INDEX ix_pb_player_pro_new RENAME TO ix_pb_player_pro"))
    connection.execute(
        sa.text(
            "ALTER INDEX ix_record_valid_map_stage_mode_player_time_new "
            "RENAME TO ix_record_valid_map_stage_mode_player_time"
        )
    )
    connection.execute(
        sa.text(
            "ALTER INDEX ix_record_valid_pro_map_stage_mode_player_time_new "
            "RENAME TO ix_record_valid_pro_map_stage_mode_player_time"
        )
    )
    connection.execute(
        sa.text(
            "ALTER INDEX ix_record_valid_player_mode_map_stage_time_new "
            "RENAME TO ix_record_valid_player_mode_map_stage_time"
        )
    )
    connection.execute(
        sa.text(
            "ALTER INDEX ix_record_valid_pro_player_mode_map_stage_time_new "
            "RENAME TO ix_record_valid_pro_player_mode_map_stage_time"
        )
    )
    connection.execute(
        sa.text("ALTER INDEX ix_record_filter_availability_new RENAME TO ix_record_filter_availability")
    )
    connection.execute(
        sa.text("ALTER INDEX ix_record_filter_lookup_new RENAME TO ix_record_filter_lookup")
    )
    connection.execute(
        sa.text(
            "ALTER INDEX ix_record_pb_scope_course_pro_time_uuid_new "
            "RENAME TO ix_record_pb_scope_course_pro_time_uuid"
        )
    )
    connection.execute(
        sa.text(
            "ALTER INDEX ix_record_pb_player_scope_pro_course_time_new "
            "RENAME TO ix_record_pb_player_scope_pro_course_time"
        )
    )
    connection.execute(
        sa.text(
            "ALTER INDEX ix_record_pb_record_uuid_scope_pro_new "
            "RENAME TO ix_record_pb_record_uuid_scope_pro"
        )
    )
    connection.execute(
        sa.text(
            "ALTER INDEX ux_record_pb_wr_scope_course_type_new "
            "RENAME TO ux_record_pb_wr_scope_course_type"
        )
    )

    connection.execute(
        sa.text(
            """
            ALTER TABLE record_pb
            ADD CONSTRAINT record_pb_pkey
            PRIMARY KEY USING INDEX ux_record_pb_pkey_new
            """
        )
    )
    connection.execute(
        sa.text(
            "ALTER TABLE record RENAME CONSTRAINT record_mode_new_fkey TO record_mode_fkey"
        )
    )
    connection.execute(
        sa.text(
            "ALTER TABLE record_filter RENAME CONSTRAINT record_filter_mode_new_fkey TO record_filter_mode_fkey"
        )
    )

    connection.execute(sa.text("ALTER TABLE record DROP COLUMN mode_id_old"))
    connection.execute(sa.text("ALTER TABLE record_filter DROP COLUMN mode_id_old"))
    connection.execute(sa.text("ALTER TABLE record_pb DROP COLUMN scope_old"))


def _analyze(connection: Connection) -> None:
    del connection
    for table_name in ("record", "record_pb", "record_filter", "mode"):
        op.execute(f"ANALYZE {table_name}")


def _terminate_other_db_sessions(connection: Connection) -> None:
    current_pid = int(_scalar(connection, "SELECT pg_backend_pid()"))
    rows = connection.execute(
        sa.text(
            """
            SELECT pid
            FROM pg_stat_activity
            WHERE datname = current_database()
              AND pid <> :current_pid
            """
        ),
        {"current_pid": current_pid},
    ).all()
    other_pids = [int(pid) for (pid,) in rows]
    if not other_pids:
        return
    _log("Terminating %s other session(s) before enum cutover: %s", len(other_pids), other_pids)
    for pid in other_pids:
        connection.execute(
            sa.text("SELECT pg_terminate_backend(:pid)"),
            {"pid": pid},
        )


def _lock_cutover_tables(connection: Connection) -> None:
    _log("Acquiring ACCESS EXCLUSIVE locks for enum cutover")
    connection.execute(
        sa.text(
            """
            LOCK TABLE
                record_filter,
                record,
                record_pb
            IN ACCESS EXCLUSIVE MODE
            """
        )
    )


def upgrade() -> None:
    connection = op.get_bind()
    record_count = _table_count(connection, "record")
    record_filter_count = _table_count(connection, "record_filter")
    record_pb_count = _table_count(connection, "record_pb")
    _log(
        "Starting enum storage migration with row counts record=%s record_filter=%s record_pb=%s",
        record_count,
        record_filter_count,
        record_pb_count,
    )

    _ensure_kz_mode_type(connection)
    _convert_mode_name_short_to_enum(connection)
    _add_shadow_columns(connection)
    _assert_no_unmapped_values(connection)

    with op.get_context().autocommit_block():
        _backfill_record_mode(op.get_bind())
    with op.get_context().autocommit_block():
        _backfill_record_filter_mode(op.get_bind())
    with op.get_context().autocommit_block():
        _backfill_record_pb_scope(op.get_bind())

    _assert_shadow_column_state(
        op.get_bind(),
        record_count=record_count,
        record_filter_count=record_filter_count,
        record_pb_count=record_pb_count,
    )

    with op.get_context().autocommit_block():
        _create_concurrent_indexes(op.get_bind())

    _add_and_validate_foreign_keys(op.get_bind())
    _terminate_other_db_sessions(op.get_bind())
    _lock_cutover_tables(op.get_bind())
    _cutover(op.get_bind())
    _assert_post_cutover_state(
        op.get_bind(),
        record_count=record_count,
        record_filter_count=record_filter_count,
        record_pb_count=record_pb_count,
    )

    with op.get_context().autocommit_block():
        _analyze(op.get_bind())


def downgrade() -> None:
    raise RuntimeError("Downgrade is not supported for this enum storage migration")
