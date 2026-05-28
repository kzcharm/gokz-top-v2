import argparse
import asyncio
import gzip
import logging
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, TextIO

from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import async_session_maker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 5_000
TEMP_USER_TABLE_NAME = "tmp_v1_user_import"
TEMP_PLAYER_TABLE_NAME = "tmp_v1_user_player_import"
MAX_V2_PLAYER_ALIAS_LENGTH = 25
MAX_V2_PLAYER_COUNTRY_LENGTH = 2

_REQUIRED_USER_COPY_COLUMNS = {
    "steamid64",
    "created_at",
    "last_seen",
}
_REQUIRED_PLAYER_COPY_COLUMNS = {
    "steamid64",
    "name",
    "alias",
    "country",
    "created_at",
    "last_seen",
    "updated_at",
}


@dataclass(frozen=True, slots=True)
class V1UserRow:
    steamid64: int
    created_at: datetime | None
    last_seen: datetime | None


@dataclass(frozen=True, slots=True)
class V1UserPlayerRow:
    steamid64: int
    name: str | None
    alias: str | None
    country: str | None
    created_at: datetime | None
    last_seen: datetime | None
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class V1UsersImportSummary:
    source_users: int
    source_players: int
    users_before: int
    users_after: int
    inserted_users: int
    timestamp_updated_users: int
    missing_players: int
    player_source_rows_for_missing_players: int
    fallback_players: int
    created_players: int
    dry_run: bool


CopyTarget = Literal["user", "player"]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Import gokz-top v1 website users from a PostgreSQL SQL dump into v2. "
            "Roles, superuser state, and active state are intentionally not imported."
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
        help="Rows to insert into temporary staging tables per batch.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Load and summarize the import without committing any changes.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the import. Required unless --dry-run is set.",
    )
    return parser


def _open_dump(path: Path) -> TextIO:
    if path.suffix == ".gz":
        return gzip.open(path, mode="rt", encoding="utf-8", newline="")
    return path.open(mode="r", encoding="utf-8", newline="")


def _parse_copy_columns(header: str, *, prefix: str) -> list[str]:
    if not header.startswith(prefix):
        raise ValueError("COPY header has an unexpected format")
    column_end = header.find(") FROM stdin;")
    if column_end == -1:
        raise ValueError("COPY header is missing FROM stdin terminator")
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


def _normalize_optional_text(raw_value: str | None) -> str | None:
    if raw_value is None:
        return None
    normalized = raw_value.strip()
    return normalized or None


def _normalize_optional_country(raw_value: str | None) -> str | None:
    normalized = _normalize_optional_text(raw_value)
    if normalized is None:
        return None
    return normalized.upper()[:MAX_V2_PLAYER_COUNTRY_LENGTH]


def _build_user_row(
    *,
    columns: list[str],
    values: list[str | None],
    line_number: int,
) -> V1UserRow:
    row = dict(zip(columns, values, strict=True))
    raw_steamid64 = row["steamid64"]
    if raw_steamid64 is None:
        raise ValueError(f"line {line_number}: user steamid64 must not be NULL")
    return V1UserRow(
        steamid64=int(raw_steamid64),
        created_at=_normalize_optional_datetime(row["created_at"]),
        last_seen=_normalize_optional_datetime(row["last_seen"]),
    )


def _build_player_row(
    *,
    columns: list[str],
    values: list[str | None],
    line_number: int,
) -> V1UserPlayerRow:
    row = dict(zip(columns, values, strict=True))
    raw_steamid64 = row["steamid64"]
    if raw_steamid64 is None:
        raise ValueError(f"line {line_number}: player steamid64 must not be NULL")
    return V1UserPlayerRow(
        steamid64=int(raw_steamid64),
        name=_normalize_optional_text(row["name"]),
        alias=_normalize_optional_text(row["alias"]),
        country=_normalize_optional_country(row["country"]),
        created_at=_normalize_optional_datetime(row["created_at"]),
        last_seen=_normalize_optional_datetime(row["last_seen"]),
        updated_at=_normalize_optional_datetime(row["updated_at"]),
    )


def _iter_copy_rows(
    path: Path,
    *,
    target: CopyTarget,
) -> Iterator[V1UserRow | V1UserPlayerRow]:
    user_prefix = 'COPY public."user" ('
    player_prefix = "COPY public.player ("
    expected_prefix = user_prefix if target == "user" else player_prefix
    required_columns = (
        _REQUIRED_USER_COPY_COLUMNS if target == "user" else _REQUIRED_PLAYER_COPY_COLUMNS
    )

    with _open_dump(path) as stream:
        columns: list[str] | None = None
        for line_number, raw_line in enumerate(stream, start=1):
            line = raw_line.rstrip("\n")
            if columns is None:
                if line.startswith(expected_prefix):
                    columns = _parse_copy_columns(line, prefix=expected_prefix)
                    missing_columns = required_columns - set(columns)
                    if missing_columns:
                        missing = ", ".join(sorted(missing_columns))
                        raise ValueError(f"{target} COPY is missing columns: {missing}")
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
            if target == "user":
                yield _build_user_row(
                    columns=columns,
                    values=values,
                    line_number=line_number,
                )
            else:
                yield _build_player_row(
                    columns=columns,
                    values=values,
                    line_number=line_number,
                )

    raise ValueError(f"dump does not contain COPY public.{target} data")


def iter_v1_user_rows(path: Path) -> Iterator[V1UserRow]:
    for row in _iter_copy_rows(path, target="user"):
        if not isinstance(row, V1UserRow):
            raise TypeError("expected V1UserRow")
        yield row


def iter_v1_user_player_rows(path: Path) -> Iterator[V1UserPlayerRow]:
    for row in _iter_copy_rows(path, target="player"):
        if not isinstance(row, V1UserPlayerRow):
            raise TypeError("expected V1UserPlayerRow")
        yield row


def _user_row_to_insert_params(row: V1UserRow) -> dict[str, object]:
    return {
        "steamid64": row.steamid64,
        "created_at": row.created_at,
        "last_seen": row.last_seen,
    }


def _player_row_to_insert_params(row: V1UserPlayerRow) -> dict[str, object]:
    return {
        "steamid64": row.steamid64,
        "name": row.name,
        "alias": row.alias,
        "country": row.country,
        "created_at": row.created_at,
        "last_seen": row.last_seen,
        "updated_at": row.updated_at,
    }


async def _create_temp_tables(session: AsyncSession) -> None:
    await session.execute(text(f"DROP TABLE IF EXISTS {TEMP_USER_TABLE_NAME}"))
    await session.execute(text(f"DROP TABLE IF EXISTS {TEMP_PLAYER_TABLE_NAME}"))
    await session.execute(
        text(
            f"""
            CREATE TEMP TABLE {TEMP_USER_TABLE_NAME} (
                steamid64 BIGINT PRIMARY KEY,
                created_at TIMESTAMPTZ,
                last_seen TIMESTAMPTZ
            ) ON COMMIT DROP
            """
        )
    )
    await session.execute(
        text(
            f"""
            CREATE TEMP TABLE {TEMP_PLAYER_TABLE_NAME} (
                steamid64 BIGINT PRIMARY KEY,
                name TEXT,
                alias TEXT,
                country VARCHAR(2),
                created_at TIMESTAMPTZ,
                last_seen TIMESTAMPTZ,
                updated_at TIMESTAMPTZ
            ) ON COMMIT DROP
            """
        )
    )


async def _load_temp_users(
    *,
    session: AsyncSession,
    dump_path: Path,
    batch_size: int,
) -> int:
    total_rows = 0
    batch: list[dict[str, object]] = []
    insert_statement = text(
        f"""
        INSERT INTO {TEMP_USER_TABLE_NAME} (
            steamid64,
            created_at,
            last_seen
        ) VALUES (
            :steamid64,
            :created_at,
            :last_seen
        )
        ON CONFLICT (steamid64) DO UPDATE SET
            created_at = CASE
                WHEN {TEMP_USER_TABLE_NAME}.created_at IS NULL THEN EXCLUDED.created_at
                WHEN EXCLUDED.created_at IS NULL THEN {TEMP_USER_TABLE_NAME}.created_at
                ELSE LEAST({TEMP_USER_TABLE_NAME}.created_at, EXCLUDED.created_at)
            END,
            last_seen = CASE
                WHEN {TEMP_USER_TABLE_NAME}.last_seen IS NULL THEN EXCLUDED.last_seen
                WHEN EXCLUDED.last_seen IS NULL THEN {TEMP_USER_TABLE_NAME}.last_seen
                ELSE GREATEST({TEMP_USER_TABLE_NAME}.last_seen, EXCLUDED.last_seen)
            END
        """
    )

    for row in iter_v1_user_rows(dump_path):
        total_rows += 1
        batch.append(_user_row_to_insert_params(row))
        if len(batch) >= batch_size:
            await session.execute(insert_statement, batch)
            logger.info("Loaded %s v1 user rows into staging", total_rows)
            batch = []

    if batch:
        await session.execute(insert_statement, batch)

    return total_rows


async def _load_temp_players(
    *,
    session: AsyncSession,
    dump_path: Path,
    batch_size: int,
    wanted_steamid64s: set[int],
) -> int:
    total_rows = 0
    batch: list[dict[str, object]] = []
    insert_statement = text(
        f"""
        INSERT INTO {TEMP_PLAYER_TABLE_NAME} (
            steamid64,
            name,
            alias,
            country,
            created_at,
            last_seen,
            updated_at
        ) VALUES (
            :steamid64,
            :name,
            :alias,
            :country,
            :created_at,
            :last_seen,
            :updated_at
        )
        ON CONFLICT (steamid64) DO UPDATE SET
            name = COALESCE(EXCLUDED.name, {TEMP_PLAYER_TABLE_NAME}.name),
            alias = COALESCE(EXCLUDED.alias, {TEMP_PLAYER_TABLE_NAME}.alias),
            country = COALESCE(EXCLUDED.country, {TEMP_PLAYER_TABLE_NAME}.country),
            created_at = CASE
                WHEN {TEMP_PLAYER_TABLE_NAME}.created_at IS NULL THEN EXCLUDED.created_at
                WHEN EXCLUDED.created_at IS NULL THEN {TEMP_PLAYER_TABLE_NAME}.created_at
                ELSE LEAST({TEMP_PLAYER_TABLE_NAME}.created_at, EXCLUDED.created_at)
            END,
            last_seen = CASE
                WHEN {TEMP_PLAYER_TABLE_NAME}.last_seen IS NULL THEN EXCLUDED.last_seen
                WHEN EXCLUDED.last_seen IS NULL THEN {TEMP_PLAYER_TABLE_NAME}.last_seen
                ELSE GREATEST({TEMP_PLAYER_TABLE_NAME}.last_seen, EXCLUDED.last_seen)
            END,
            updated_at = CASE
                WHEN {TEMP_PLAYER_TABLE_NAME}.updated_at IS NULL THEN EXCLUDED.updated_at
                WHEN EXCLUDED.updated_at IS NULL THEN {TEMP_PLAYER_TABLE_NAME}.updated_at
                ELSE GREATEST({TEMP_PLAYER_TABLE_NAME}.updated_at, EXCLUDED.updated_at)
            END
        """
    )

    for row in iter_v1_user_player_rows(dump_path):
        if row.steamid64 not in wanted_steamid64s:
            continue

        total_rows += 1
        batch.append(_player_row_to_insert_params(row))
        if len(batch) >= batch_size:
            await session.execute(insert_statement, batch)
            logger.info("Loaded %s v1 player rows into user import staging", total_rows)
            batch = []

    if batch:
        await session.execute(insert_statement, batch)

    return total_rows


async def _get_staged_user_steamid64s(session: AsyncSession) -> set[int]:
    rows = (
        await session.execute(
            text(
                f"""
                SELECT steamid64
                FROM {TEMP_USER_TABLE_NAME}
                """
            )
        )
    ).all()
    return {int(row.steamid64) for row in rows}


async def _scalar_int(session: AsyncSession, sql: str) -> int:
    value = (await session.execute(text(sql))).scalar_one()
    return int(value)


async def _summarize_staged_import(
    *,
    session: AsyncSession,
    source_users: int,
    source_players: int,
    dry_run: bool,
) -> V1UsersImportSummary:
    users_before = await _scalar_int(session, 'SELECT count(*) FROM "user"')
    inserted_users = await _scalar_int(
        session,
        f"""
        SELECT count(*)
        FROM {TEMP_USER_TABLE_NAME} source
        LEFT JOIN "user" target ON target.steamid64 = source.steamid64
        WHERE target.steamid64 IS NULL
        """,
    )
    timestamp_updated_users = await _scalar_int(
        session,
        f"""
        SELECT count(*)
        FROM {TEMP_USER_TABLE_NAME} source
        JOIN "user" target ON target.steamid64 = source.steamid64
        WHERE target.created_at IS DISTINCT FROM
            CASE
                WHEN target.created_at IS NULL THEN source.created_at
                WHEN source.created_at IS NULL THEN target.created_at
                ELSE LEAST(target.created_at, source.created_at)
            END
          OR target.last_visited_at IS DISTINCT FROM
            CASE
                WHEN target.last_visited_at IS NULL THEN source.last_seen
                WHEN source.last_seen IS NULL THEN target.last_visited_at
                ELSE GREATEST(target.last_visited_at, source.last_seen)
            END
        """,
    )
    missing_players = await _scalar_int(
        session,
        f"""
        SELECT count(*)
        FROM {TEMP_USER_TABLE_NAME} source
        LEFT JOIN player target ON target.steamid64 = source.steamid64
        WHERE target.steamid64 IS NULL
        """,
    )
    player_source_rows_for_missing_players = await _scalar_int(
        session,
        f"""
        SELECT count(*)
        FROM {TEMP_USER_TABLE_NAME} source
        JOIN {TEMP_PLAYER_TABLE_NAME} player_source
          ON player_source.steamid64 = source.steamid64
        LEFT JOIN player target ON target.steamid64 = source.steamid64
        WHERE target.steamid64 IS NULL
        """,
    )
    fallback_players = missing_players - player_source_rows_for_missing_players
    return V1UsersImportSummary(
        source_users=source_users,
        source_players=source_players,
        users_before=users_before,
        users_after=users_before + inserted_users,
        inserted_users=inserted_users,
        timestamp_updated_users=timestamp_updated_users,
        missing_players=missing_players,
        player_source_rows_for_missing_players=player_source_rows_for_missing_players,
        fallback_players=fallback_players,
        created_players=missing_players,
        dry_run=dry_run,
    )


async def _apply_staged_import(session: AsyncSession) -> None:
    await session.execute(
        text(
            f"""
            INSERT INTO player (
                steamid64,
                name,
                alias,
                country,
                created_at,
                last_played_at,
                updated_at
            )
            SELECT
                source.steamid64,
                COALESCE(NULLIF(btrim(player_source.name), ''), source.steamid64::text),
                CASE
                    WHEN player_source.alias IS NULL THEN NULL
                    ELSE nullif(btrim(left(player_source.alias, {MAX_V2_PLAYER_ALIAS_LENGTH})), '')
                END,
                player_source.country,
                COALESCE(player_source.created_at, source.created_at, now()),
                player_source.last_seen,
                COALESCE(player_source.updated_at, player_source.created_at, source.created_at, now())
            FROM {TEMP_USER_TABLE_NAME} source
            LEFT JOIN {TEMP_PLAYER_TABLE_NAME} player_source
              ON player_source.steamid64 = source.steamid64
            LEFT JOIN player target ON target.steamid64 = source.steamid64
            WHERE target.steamid64 IS NULL
            """
        )
    )
    await session.execute(
        text(
            f"""
            INSERT INTO "user" (
                steamid64,
                is_active,
                roles,
                created_at,
                last_visited_at
            )
            SELECT
                source.steamid64,
                true,
                ARRAY[]::user_role[],
                source.created_at,
                source.last_seen
            FROM {TEMP_USER_TABLE_NAME} source
            ON CONFLICT (steamid64) DO UPDATE SET
                created_at = CASE
                    WHEN "user".created_at IS NULL THEN EXCLUDED.created_at
                    WHEN EXCLUDED.created_at IS NULL THEN "user".created_at
                    ELSE LEAST("user".created_at, EXCLUDED.created_at)
                END,
                last_visited_at = CASE
                    WHEN "user".last_visited_at IS NULL THEN EXCLUDED.last_visited_at
                    WHEN EXCLUDED.last_visited_at IS NULL THEN "user".last_visited_at
                    ELSE GREATEST("user".last_visited_at, EXCLUDED.last_visited_at)
                END
            """
        )
    )


async def import_v1_users(
    *,
    session: AsyncSession,
    dump_path: Path,
    dry_run: bool,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> V1UsersImportSummary:
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")

    await _create_temp_tables(session)
    source_users = await _load_temp_users(
        session=session,
        dump_path=dump_path,
        batch_size=batch_size,
    )
    source_players = await _load_temp_players(
        session=session,
        dump_path=dump_path,
        batch_size=batch_size,
        wanted_steamid64s=await _get_staged_user_steamid64s(session),
    )
    summary = await _summarize_staged_import(
        session=session,
        source_users=source_users,
        source_players=source_players,
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
    if args.dry_run == args.apply:
        raise ValueError("Specify exactly one of --dry-run or --apply")

    dump_path = args.dump.resolve()
    if not dump_path.is_file():
        raise FileNotFoundError(dump_path)

    async with async_session_maker() as session:
        summary = await import_v1_users(
            session=session,
            dump_path=dump_path,
            dry_run=args.dry_run,
            batch_size=args.batch_size,
        )

    logger.info("v1 user import dry_run=%s", summary.dry_run)
    logger.info("Source users: %s", summary.source_users)
    logger.info("Source players scanned: %s", summary.source_players)
    logger.info("Users before: %s", summary.users_before)
    logger.info("Users after: %s", summary.users_after)
    logger.info("Inserted users: %s", summary.inserted_users)
    logger.info("Timestamp-updated existing users: %s", summary.timestamp_updated_users)
    logger.info("Missing players to create: %s", summary.missing_players)
    logger.info(
        "Missing players with v1 player source rows: %s",
        summary.player_source_rows_for_missing_players,
    )
    logger.info("Fallback players from SteamID64 only: %s", summary.fallback_players)
    logger.info("Created players: %s", summary.created_players)


def main(argv: list[str] | None = None) -> None:
    asyncio.run(_main_async(argv))


if __name__ == "__main__":
    main()
