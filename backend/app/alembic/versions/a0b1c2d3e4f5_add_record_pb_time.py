"""add record pb time and type

Revision ID: a0b1c2d3e4f5
Revises: 9d2a6d0d5f2d
Create Date: 2026-05-26 00:00:00.000000

"""

from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine import Connection, RowMapping

revision = "a0b1c2d3e4f5"
down_revision = "9d2a6d0d5f2d"
branch_labels = None
depends_on = None

RECORD_PB_TIME_BATCH_SIZE = 100_000

OLD_RECORD_PB_INDEXES = (
    "ix_record_pb_scope_course_pro_record_uuid",
    "ix_record_pb_scope_course_pro_time_record_uuid",
    "ix_record_pb_player_scope_pro_course_record_uuid",
    "ix_record_pb_record_uuid_scope_pro",
    "ux_record_pb_wr_scope_course_type",
)

NEW_RECORD_PB_INDEX_DEFINITIONS = (
    """
    CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_record_pb_scope_course_type_record_uuid
    ON record_pb (scope, course_id, type, record_uuid)
    """,
    """
    CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_record_pb_scope_course_type_time_record_uuid
    ON record_pb (scope, course_id, type, time, record_uuid)
    """,
    """
    CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_record_pb_player_scope_type_course_record_uuid
    ON record_pb (steamid64, scope, type, course_id, record_uuid)
    """,
    """
    CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_record_pb_record_uuid_scope_type
    ON record_pb (record_uuid, scope, type)
    """,
)

NEW_RECORD_PB_WR_INDEX_DEFINITION = """
    CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ux_record_pb_wr_scope_course_type
    ON record_pb (scope, course_id, type)
    WHERE points = 1000
    """


def _mapping_row(connection: Connection, sql: str, **params: Any) -> RowMapping:
    return connection.execute(sa.text(sql), params).mappings().one()


def _backfill_record_pb_columns(connection: Connection) -> None:
    last_scope: str | None = None
    last_course_id: int | None = None
    last_steamid64: int | None = None
    last_is_pro_only: bool | None = None
    while True:
        cursor_filter = ""
        params: dict[str, Any] = {"batch_size": RECORD_PB_TIME_BATCH_SIZE}
        if last_scope is not None:
            cursor_filter = """
                  AND (scope, course_id, steamid64, is_pro_only) > (
                        CAST(:last_scope AS mode_scope),
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
                SELECT scope, course_id, steamid64, is_pro_only, record_uuid
                FROM record_pb
                WHERE time IS NULL OR type IS NULL
                  {cursor_filter}
                ORDER BY scope, course_id, steamid64, is_pro_only
                LIMIT :batch_size
            ),
            updated AS (
                UPDATE record_pb
                SET
                    time = COALESCE(record_pb.time, record.time),
                    type = COALESCE(
                        record_pb.type,
                        CASE
                            WHEN record_pb.is_pro_only THEN 'PRO'::record_type
                            ELSE 'NUB'::record_type
                        END
                    )
                FROM batch
                JOIN record
                  ON record.uuid = batch.record_uuid
                WHERE record_pb.scope = batch.scope
                  AND record_pb.course_id = batch.course_id
                  AND record_pb.steamid64 = batch.steamid64
                  AND record_pb.is_pro_only = batch.is_pro_only
                RETURNING record_pb.scope
            )
            SELECT
                COALESCE((SELECT COUNT(*) FROM updated), 0) AS updated_rows,
                (
                    SELECT scope::text
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
        last_scope = str(row["last_scope"])
        last_course_id = int(row["last_course_id"])
        last_steamid64 = int(row["last_steamid64"])
        last_is_pro_only = bool(row["last_is_pro_only"])


def upgrade() -> None:
    op.execute("ALTER TABLE record_pb ADD COLUMN IF NOT EXISTS time NUMERIC(12, 3)")
    op.execute('ALTER TABLE record_pb ADD COLUMN IF NOT EXISTS "type" record_type')
    _backfill_record_pb_columns(op.get_bind())
    op.execute("ALTER TABLE record_pb ALTER COLUMN time SET NOT NULL")
    op.execute('ALTER TABLE record_pb ALTER COLUMN "type" SET NOT NULL')
    with op.get_context().autocommit_block():
        op.execute(
            """
            CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ux_record_pb_pk_type
            ON record_pb (scope, course_id, steamid64, type)
            """
        )
        for index_definition in NEW_RECORD_PB_INDEX_DEFINITIONS:
            op.execute(index_definition)
        for index_name in OLD_RECORD_PB_INDEXES:
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {index_name}")
        op.execute(NEW_RECORD_PB_WR_INDEX_DEFINITION)

    op.execute("ALTER TABLE record_pb DROP CONSTRAINT IF EXISTS record_pb_pkey")
    op.execute(
        """
        ALTER TABLE record_pb
        ADD CONSTRAINT record_pb_pkey PRIMARY KEY USING INDEX ux_record_pb_pk_type
        """
    )
    op.execute("ALTER TABLE record_pb DROP COLUMN IF EXISTS is_pro_only")


def downgrade() -> None:
    op.execute("ALTER TABLE record_pb ADD COLUMN IF NOT EXISTS is_pro_only boolean")
    op.execute(
        """
        UPDATE record_pb
        SET is_pro_only = (type = 'PRO'::record_type)
        WHERE is_pro_only IS NULL
        """
    )
    op.execute("ALTER TABLE record_pb ALTER COLUMN is_pro_only SET NOT NULL")
    with op.get_context().autocommit_block():
        op.execute(
            """
            CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ux_record_pb_pk_is_pro_only
            ON record_pb (scope, course_id, steamid64, is_pro_only)
            """
        )
        for index_name in (
            "ix_record_pb_scope_course_type_record_uuid",
            "ix_record_pb_scope_course_type_time_record_uuid",
            "ix_record_pb_player_scope_type_course_record_uuid",
            "ix_record_pb_record_uuid_scope_type",
            "ux_record_pb_wr_scope_course_type",
        ):
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {index_name}")
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_record_pb_scope_course_pro_record_uuid
            ON record_pb (scope, course_id, is_pro_only, record_uuid)
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_record_pb_player_scope_pro_course_record_uuid
            ON record_pb (steamid64, scope, is_pro_only, course_id, record_uuid)
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_record_pb_record_uuid_scope_pro
            ON record_pb (record_uuid, scope, is_pro_only)
            """
        )
        op.execute(
            """
            CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ux_record_pb_wr_scope_course_type
            ON record_pb (scope, course_id, is_pro_only)
            WHERE points = 1000
            """
        )

    op.execute("ALTER TABLE record_pb DROP CONSTRAINT IF EXISTS record_pb_pkey")
    op.execute(
        """
        ALTER TABLE record_pb
        ADD CONSTRAINT record_pb_pkey PRIMARY KEY USING INDEX ux_record_pb_pk_is_pro_only
        """
    )
    op.execute('ALTER TABLE record_pb DROP COLUMN IF EXISTS "type"')
    op.execute("ALTER TABLE record_pb DROP COLUMN IF EXISTS time")
