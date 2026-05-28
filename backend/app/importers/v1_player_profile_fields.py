import argparse
import asyncio
import gzip
import logging
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import async_session_maker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 5_000
MAX_V2_ALIAS_LENGTH = 25
TEMP_TABLE_NAME = "tmp_v1_player_profile_import"

_REQUIRED_PLAYER_COPY_COLUMNS = {
    "steamid64",
    "country",
    "alias",
    "updated_at",
    "created_at",
    "is_country_locked",
    "alias_updated_at",
}


@dataclass(frozen=True, slots=True)
class V1PlayerProfileRow:
    steamid64: int
    alias: str | None
    country: str | None
    is_country_locked: bool
    alias_updated_at: datetime | None
    updated_at: datetime | None
    created_at: datetime | None


@dataclass(frozen=True, slots=True)
class V1PlayerProfileImportSummary:
    source_rows: int
    matched_rows: int
    skipped_missing_players: int
    alias_changed_rows: int
    country_changed_rows: int
    country_lock_upsert_rows: int
    country_lock_delete_rows: int
    alias_action_upsert_rows: int
    truncated_alias_rows: int
    dry_run: bool


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Import gokz-top v1 player alias, country, and country-lock fields "
            "from a PostgreSQL SQL dump into existing v2 players."
        )
    )
    parser.add_argument(
        "--dump",
        type=Path,
        required=True,
        help="Path to the gokz-top v1 PostgreSQL .sql or .sql.gz dump.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="Rows to insert into the temporary staging table per batch.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Load and summarize the import without committing any changes.",
    )
    return parser


def _open_dump(path: Path) -> TextIO:
    if path.suffix == ".gz":
        return gzip.open(path, mode="rt", encoding="utf-8", newline="")
    return path.open(mode="r", encoding="utf-8", newline="")


def _parse_copy_columns(header: str) -> list[str]:
    prefix = "COPY public.player ("
    if not header.startswith(prefix):
        raise ValueError("player COPY header has an unexpected format")
    column_end = header.find(") FROM stdin;")
    if column_end == -1:
        raise ValueError("player COPY header is missing FROM stdin terminator")
    return [column.strip() for column in header[len(prefix) : column_end].split(",")]


def _unescape_copy_text(value: str) -> str:
    result: list[str] = []
    index = 0
    while index < len(value):
        char = value[index]
        if char != "\\":
            result.append(char)
            index += 1
            continue

        index += 1
        if index >= len(value):
            result.append("\\")
            break

        escaped = value[index]
        index += 1
        mapped = {
            "b": "\b",
            "f": "\f",
            "n": "\n",
            "r": "\r",
            "t": "\t",
            "v": "\v",
            "\\": "\\",
        }.get(escaped)
        if mapped is not None:
            result.append(mapped)
            continue

        if escaped in {"x", "X"} and index + 1 < len(value):
            hex_candidate = value[index : index + 2]
            try:
                result.append(chr(int(hex_candidate, 16)))
            except ValueError:
                result.append(escaped)
            else:
                index += 2
            continue

        if escaped.isdigit():
            octal_digits = [escaped]
            while (
                index < len(value)
                and len(octal_digits) < 3
                and value[index] in "01234567"
            ):
                octal_digits.append(value[index])
                index += 1
            result.append(chr(int("".join(octal_digits), 8)))
            continue

        result.append(escaped)

    return "".join(result)


def _parse_copy_value(raw_value: str) -> str | None:
    if raw_value == r"\N":
        return None
    return _unescape_copy_text(raw_value)


def _normalize_optional_datetime(raw_value: str | None) -> datetime | None:
    if raw_value is None:
        return None
    normalized = raw_value.strip()
    if not normalized:
        return None

    parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _normalize_optional_country(raw_value: str | None) -> str | None:
    if raw_value is None:
        return None
    normalized = raw_value.strip().upper()
    return normalized or None


def _normalize_bool(raw_value: str | None, *, field_name: str) -> bool:
    if raw_value in {"t", "true", "1"}:
        return True
    if raw_value in {"f", "false", "0"}:
        return False
    raise ValueError(f"{field_name} must be a PostgreSQL boolean value")


def _build_player_row(
    *,
    columns: list[str],
    values: list[str | None],
    line_number: int,
) -> V1PlayerProfileRow:
    row = dict(zip(columns, values, strict=True))
    raw_steamid64 = row["steamid64"]
    if raw_steamid64 is None:
        raise ValueError(f"line {line_number}: steamid64 must not be NULL")

    return V1PlayerProfileRow(
        steamid64=int(raw_steamid64),
        alias=row["alias"],
        country=_normalize_optional_country(row["country"]),
        is_country_locked=_normalize_bool(
            row["is_country_locked"],
            field_name=f"line {line_number}: is_country_locked",
        ),
        alias_updated_at=_normalize_optional_datetime(row["alias_updated_at"]),
        updated_at=_normalize_optional_datetime(row["updated_at"]),
        created_at=_normalize_optional_datetime(row["created_at"]),
    )


def iter_v1_player_profile_rows(path: Path) -> Iterator[V1PlayerProfileRow]:
    with _open_dump(path) as stream:
        columns: list[str] | None = None
        for line_number, raw_line in enumerate(stream, start=1):
            line = raw_line.rstrip("\n")
            if columns is None:
                if line.startswith("COPY public.player ("):
                    columns = _parse_copy_columns(line)
                    missing_columns = _REQUIRED_PLAYER_COPY_COLUMNS - set(columns)
                    if missing_columns:
                        missing = ", ".join(sorted(missing_columns))
                        raise ValueError(f"player COPY is missing columns: {missing}")
                continue

            if line == r"\.":
                return

            raw_values = line.split("\t")
            if len(raw_values) != len(columns):
                raise ValueError(
                    f"line {line_number}: expected {len(columns)} fields, "
                    f"found {len(raw_values)}"
                )
            values = [_parse_copy_value(value) for value in raw_values]
            yield _build_player_row(
                columns=columns,
                values=values,
                line_number=line_number,
            )

    raise ValueError("dump does not contain COPY public.player data")


def _row_to_insert_params(row: V1PlayerProfileRow) -> dict[str, object]:
    return {
        "steamid64": row.steamid64,
        "alias": row.alias,
        "country": row.country,
        "is_country_locked": row.is_country_locked,
        "alias_updated_at": row.alias_updated_at,
        "updated_at": row.updated_at,
        "created_at": row.created_at,
    }


async def _create_temp_table(session: AsyncSession) -> None:
    await session.execute(
        text(
            f"""
            CREATE TEMP TABLE {TEMP_TABLE_NAME} (
                steamid64 BIGINT PRIMARY KEY,
                alias TEXT,
                country VARCHAR(2),
                is_country_locked BOOLEAN NOT NULL,
                alias_updated_at TIMESTAMPTZ,
                updated_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ
            ) ON COMMIT DROP
            """
        )
    )


async def _load_temp_table(
    *,
    session: AsyncSession,
    dump_path: Path,
    batch_size: int,
) -> int:
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")

    total_rows = 0
    batch: list[dict[str, object]] = []
    insert_statement = text(
        f"""
        INSERT INTO {TEMP_TABLE_NAME} (
            steamid64,
            alias,
            country,
            is_country_locked,
            alias_updated_at,
            updated_at,
            created_at
        ) VALUES (
            :steamid64,
            :alias,
            :country,
            :is_country_locked,
            :alias_updated_at,
            :updated_at,
            :created_at
        )
        ON CONFLICT (steamid64) DO UPDATE SET
            alias = EXCLUDED.alias,
            country = EXCLUDED.country,
            is_country_locked = EXCLUDED.is_country_locked,
            alias_updated_at = EXCLUDED.alias_updated_at,
            updated_at = EXCLUDED.updated_at,
            created_at = EXCLUDED.created_at
        """
    )

    for row in iter_v1_player_profile_rows(dump_path):
        total_rows += 1
        batch.append(_row_to_insert_params(row))
        if len(batch) >= batch_size:
            await session.execute(insert_statement, batch)
            logger.info("Loaded %s v1 player rows into staging", total_rows)
            batch = []

    if batch:
        await session.execute(insert_statement, batch)

    return total_rows


async def _scalar_int(session: AsyncSession, sql: str) -> int:
    value = (await session.execute(text(sql))).scalar_one()
    return int(value)


async def _summarize_staged_import(
    *,
    session: AsyncSession,
    source_rows: int,
    dry_run: bool,
) -> V1PlayerProfileImportSummary:
    matched_rows = await _scalar_int(
        session,
        f"""
        SELECT count(*)
        FROM {TEMP_TABLE_NAME} source
        JOIN player ON player.steamid64 = source.steamid64
        """,
    )
    truncated_alias_rows = await _scalar_int(
        session,
        f"""
        SELECT count(*)
        FROM {TEMP_TABLE_NAME} source
        JOIN player ON player.steamid64 = source.steamid64
        WHERE source.alias IS NOT NULL
          AND length(source.alias) > {MAX_V2_ALIAS_LENGTH}
        """,
    )
    alias_changed_rows = await _scalar_int(
        session,
        f"""
        SELECT count(*)
        FROM {TEMP_TABLE_NAME} source
        JOIN player ON player.steamid64 = source.steamid64
        WHERE player.alias IS DISTINCT FROM
            CASE
                WHEN source.alias IS NULL THEN NULL
                ELSE nullif(btrim(left(source.alias, {MAX_V2_ALIAS_LENGTH})), '')
            END
        """,
    )
    country_changed_rows = await _scalar_int(
        session,
        f"""
        SELECT count(*)
        FROM {TEMP_TABLE_NAME} source
        JOIN player ON player.steamid64 = source.steamid64
        WHERE player.country IS DISTINCT FROM source.country
        """,
    )
    country_lock_upsert_rows = await _scalar_int(
        session,
        f"""
        SELECT count(*)
        FROM {TEMP_TABLE_NAME} source
        JOIN player ON player.steamid64 = source.steamid64
        LEFT JOIN player_action_timestamp action_timestamp
          ON action_timestamp.player_steamid64 = source.steamid64
         AND action_timestamp.action = 'country_manual_override'::player_action
        WHERE source.is_country_locked = true
          AND (
              action_timestamp.player_steamid64 IS NULL
              OR action_timestamp.recorded_at IS DISTINCT FROM
                 COALESCE(source.updated_at, source.created_at, now())
          )
        """,
    )
    country_lock_delete_rows = await _scalar_int(
        session,
        f"""
        SELECT count(*)
        FROM {TEMP_TABLE_NAME} source
        JOIN player ON player.steamid64 = source.steamid64
        JOIN player_action_timestamp action_timestamp
          ON action_timestamp.player_steamid64 = source.steamid64
         AND action_timestamp.action = 'country_manual_override'::player_action
        WHERE source.is_country_locked = false
        """,
    )
    alias_action_upsert_rows = await _scalar_int(
        session,
        f"""
        SELECT count(*)
        FROM {TEMP_TABLE_NAME} source
        JOIN player ON player.steamid64 = source.steamid64
        LEFT JOIN player_action_timestamp action_timestamp
          ON action_timestamp.player_steamid64 = source.steamid64
         AND action_timestamp.action = 'alias_change'::player_action
        WHERE source.alias_updated_at IS NOT NULL
          AND (
              action_timestamp.player_steamid64 IS NULL
              OR action_timestamp.recorded_at IS DISTINCT FROM source.alias_updated_at
          )
        """,
    )
    return V1PlayerProfileImportSummary(
        source_rows=source_rows,
        matched_rows=matched_rows,
        skipped_missing_players=source_rows - matched_rows,
        alias_changed_rows=alias_changed_rows,
        country_changed_rows=country_changed_rows,
        country_lock_upsert_rows=country_lock_upsert_rows,
        country_lock_delete_rows=country_lock_delete_rows,
        alias_action_upsert_rows=alias_action_upsert_rows,
        truncated_alias_rows=truncated_alias_rows,
        dry_run=dry_run,
    )


async def _apply_staged_import(session: AsyncSession) -> None:
    await session.execute(
        text(
            f"""
            UPDATE player
            SET
                alias = CASE
                    WHEN source.alias IS NULL THEN NULL
                    ELSE nullif(btrim(left(source.alias, {MAX_V2_ALIAS_LENGTH})), '')
                END,
                country = source.country,
                updated_at = now()
            FROM {TEMP_TABLE_NAME} source
            WHERE player.steamid64 = source.steamid64
              AND (
                  player.alias IS DISTINCT FROM
                      CASE
                          WHEN source.alias IS NULL THEN NULL
                          ELSE nullif(btrim(left(source.alias, {MAX_V2_ALIAS_LENGTH})), '')
                      END
                  OR player.country IS DISTINCT FROM source.country
              )
            """
        )
    )
    await session.execute(
        text(
            f"""
            INSERT INTO player_action_timestamp (
                player_steamid64,
                action,
                recorded_at
            )
            SELECT
                source.steamid64,
                'country_manual_override'::player_action,
                COALESCE(source.updated_at, source.created_at, now())
            FROM {TEMP_TABLE_NAME} source
            JOIN player ON player.steamid64 = source.steamid64
            WHERE source.is_country_locked = true
            ON CONFLICT (player_steamid64, action) DO UPDATE SET
                recorded_at = EXCLUDED.recorded_at
            """
        )
    )
    await session.execute(
        text(
            f"""
            DELETE FROM player_action_timestamp action_timestamp
            USING {TEMP_TABLE_NAME} source
            JOIN player ON player.steamid64 = source.steamid64
            WHERE action_timestamp.player_steamid64 = source.steamid64
              AND action_timestamp.action = 'country_manual_override'::player_action
              AND source.is_country_locked = false
            """
        )
    )
    await session.execute(
        text(
            f"""
            INSERT INTO player_action_timestamp (
                player_steamid64,
                action,
                recorded_at
            )
            SELECT
                source.steamid64,
                'alias_change'::player_action,
                source.alias_updated_at
            FROM {TEMP_TABLE_NAME} source
            JOIN player ON player.steamid64 = source.steamid64
            WHERE source.alias_updated_at IS NOT NULL
            ON CONFLICT (player_steamid64, action) DO UPDATE SET
                recorded_at = EXCLUDED.recorded_at
            """
        )
    )


async def import_v1_player_profile_fields(
    *,
    session: AsyncSession,
    dump_path: Path,
    dry_run: bool,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> V1PlayerProfileImportSummary:
    await _create_temp_table(session)
    source_rows = await _load_temp_table(
        session=session,
        dump_path=dump_path,
        batch_size=batch_size,
    )
    summary = await _summarize_staged_import(
        session=session,
        source_rows=source_rows,
        dry_run=dry_run,
    )
    if dry_run:
        await session.rollback()
        return summary

    await _apply_staged_import(session)
    await session.commit()
    return summary


async def _main_async(argv: list[str] | None = None) -> None:
    args = _build_parser().parse_args(argv)
    dump_path = args.dump.resolve()
    if not dump_path.is_file():
        raise FileNotFoundError(dump_path)

    async with async_session_maker() as session:
        summary = await import_v1_player_profile_fields(
            session=session,
            dump_path=dump_path,
            dry_run=args.dry_run,
            batch_size=args.batch_size,
        )

    logger.info("v1 player profile import dry_run=%s", summary.dry_run)
    logger.info("Source rows: %s", summary.source_rows)
    logger.info("Matched existing v2 players: %s", summary.matched_rows)
    logger.info("Skipped missing v2 players: %s", summary.skipped_missing_players)
    logger.info("Alias changes: %s", summary.alias_changed_rows)
    logger.info("Country changes: %s", summary.country_changed_rows)
    logger.info("Country lock upserts: %s", summary.country_lock_upsert_rows)
    logger.info("Country lock deletes: %s", summary.country_lock_delete_rows)
    logger.info("Alias action timestamp upserts: %s", summary.alias_action_upsert_rows)
    logger.info("Aliases truncated to v2 limit: %s", summary.truncated_alias_rows)


def main(argv: list[str] | None = None) -> None:
    asyncio.run(_main_async(argv))


if __name__ == "__main__":
    main()
