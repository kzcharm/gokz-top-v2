import zlib
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import case, func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import KZMode, Map, Player, Record, seconds_to_time_ms

STEAMID64_ACCOUNT_ID_BASE = 76_561_197_960_265_728
STEAM_ACCOUNT_ID_MAX = 4_294_967_295
GOKZ_MAP_NAME_MAX_LENGTH = 32
SQL_VALUES_BATCH_SIZE = 1_000

GOKZ_LOCAL_MODE_BY_KZ_MODE = {
    KZMode.VNL: 0,
    KZMode.SKZ: 1,
    KZMode.KZT: 2,
}


@dataclass(frozen=True)
class GokzLocalDbExportStats:
    total_rows: int
    exportable_rows: int
    invalid_rows: int
    incompatible_steamid_rows: int
    incompatible_mode_rows: int
    incompatible_map_name_rows: int

    @property
    def skipped_rows(self) -> int:
        return self.total_rows - self.exportable_rows


def _selected_record_predicates(server_ids: list[int]) -> tuple[Any, ...]:
    return (col(Record.server_id).in_(server_ids),)


def _exportable_record_predicates(server_ids: list[int]) -> tuple[Any, ...]:
    return (
        *_selected_record_predicates(server_ids),
        col(Record.is_valid).is_(True),
        col(Record.steamid64) >= STEAMID64_ACCOUNT_ID_BASE,
        col(Record.steamid64) <= STEAMID64_ACCOUNT_ID_BASE + STEAM_ACCOUNT_ID_MAX,
        col(Record.mode).in_(tuple(GOKZ_LOCAL_MODE_BY_KZ_MODE)),
        func.length(Map.name) <= GOKZ_MAP_NAME_MAX_LENGTH,
    )


async def get_gokz_localdb_export_stats(
    *, session: AsyncSession, server_ids: list[int]
) -> GokzLocalDbExportStats:
    statement = (
        select(
            func.count().label("total_rows"),
            func.count().filter(col(Record.is_valid).is_(False)).label("invalid_rows"),
            func.count()
            .filter(
                (col(Record.steamid64) < STEAMID64_ACCOUNT_ID_BASE)
                | (
                    col(Record.steamid64)
                    > STEAMID64_ACCOUNT_ID_BASE + STEAM_ACCOUNT_ID_MAX
                )
            )
            .label("incompatible_steamid_rows"),
            func.count()
            .filter(~col(Record.mode).in_(tuple(GOKZ_LOCAL_MODE_BY_KZ_MODE)))
            .label("incompatible_mode_rows"),
            func.count()
            .filter(func.length(Map.name) > GOKZ_MAP_NAME_MAX_LENGTH)
            .label("incompatible_map_name_rows"),
            func.count()
            .filter(*_exportable_record_predicates(server_ids))
            .label("exportable_rows"),
        )
        .select_from(Record)
        .join(Map, col(Map.id) == col(Record.map_id))
        .where(*_selected_record_predicates(server_ids))
    )
    row = (await session.exec(statement)).one()
    return GokzLocalDbExportStats(
        total_rows=row.total_rows,
        exportable_rows=row.exportable_rows,
        invalid_rows=row.invalid_rows,
        incompatible_steamid_rows=row.incompatible_steamid_rows,
        incompatible_mode_rows=row.incompatible_mode_rows,
        incompatible_map_name_rows=row.incompatible_map_name_rows,
    )


def _mysql_string(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace("\0", "\\0")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\x1a", "\\Z")
        .replace("'", "\\'")
    )
    return f"'{escaped}'"


def _mysql_datetime(value: datetime) -> str:
    normalized = value.astimezone(UTC) if value.tzinfo is not None else value
    return _mysql_string(normalized.strftime("%Y-%m-%d %H:%M:%S"))


async def _iter_players_sql(
    *, session: AsyncSession, server_ids: list[int]
) -> AsyncIterator[str]:
    alias = func.coalesce(col(Player.alias), col(Player.name))
    statement = (
        select(
            col(Player.steamid64),
            alias.label("alias"),
            col(Player.country),
            func.min(col(Record.created_at)).label("created_at"),
            func.max(col(Record.created_at)).label("last_played_at"),
        )
        .join(Record, col(Record.steamid64) == col(Player.steamid64))
        .join(Map, col(Map.id) == col(Record.map_id))
        .where(*_exportable_record_predicates(server_ids))
        .group_by(col(Player.steamid64), alias, col(Player.country))
        .order_by(col(Player.steamid64))
    )
    result = await session.stream(statement)
    rows = (
        "("
        + ",".join(
            (
                str(row.steamid64 - STEAMID64_ACCOUNT_ID_BASE),
                _mysql_string(row.alias[:32]),
                "NULL" if row.country is None else _mysql_string(row.country),
                "NULL",
                "0",
                _mysql_datetime(row.last_played_at),
                _mysql_datetime(row.created_at),
            )
        )
        + ")"
        async for row in result
    )
    values: list[str] = []
    async for value in rows:
        values.append(value)
        if len(values) == SQL_VALUES_BATCH_SIZE:
            yield _players_insert(values)
            values = []
    if values:
        yield _players_insert(values)


def _players_insert(values: list[str]) -> str:
    return (
        "INSERT IGNORE INTO `Players` "
        "(`SteamID32`,`Alias`,`Country`,`IP`,`Cheater`,`LastPlayed`,`Created`) VALUES\n"
        + ",\n".join(values)
        + ";\n"
    )


async def _iter_maps_sql(
    *, session: AsyncSession, server_ids: list[int]
) -> AsyncIterator[str]:
    statement = (
        select(
            col(Map.name),
            func.min(col(Record.created_at)).label("created_at"),
            func.max(col(Record.created_at)).label("last_played_at"),
        )
        .join(Record, col(Record.map_id) == col(Map.id))
        .where(*_exportable_record_predicates(server_ids))
        .group_by(col(Map.id), col(Map.name))
        .order_by(col(Map.name))
    )
    result = await session.stream(statement)
    values: list[str] = []
    async for row in result:
        values.append(
            "("
            + ",".join(
                (
                    _mysql_string(row.name),
                    _mysql_datetime(row.last_played_at),
                    _mysql_datetime(row.created_at),
                )
            )
            + ")"
        )
        if len(values) == SQL_VALUES_BATCH_SIZE:
            yield _maps_insert(values)
            values = []
    if values:
        yield _maps_insert(values)


def _maps_insert(values: list[str]) -> str:
    return (
        "INSERT IGNORE INTO `Maps` (`Name`,`LastPlayed`,`Created`) VALUES\n"
        + ",\n".join(values)
        + ";\n"
    )


async def _iter_times_sql(
    *, session: AsyncSession, server_ids: list[int]
) -> AsyncIterator[str]:
    local_mode = case(
        *(
            (col(Record.mode) == mode, local_id)
            for mode, local_id in GOKZ_LOCAL_MODE_BY_KZ_MODE.items()
        )
    )
    statement = (
        select(
            col(Record.steamid64),
            col(Map.name).label("map_name"),
            col(Record.stage),
            local_mode.label("local_mode"),
            col(Record.time),
            col(Record.teleports),
            col(Record.created_at),
        )
        .join(Map, col(Map.id) == col(Record.map_id))
        .where(*_exportable_record_predicates(server_ids))
        .order_by(col(Record.created_at), col(Record.uuid))
        .execution_options(yield_per=SQL_VALUES_BATCH_SIZE)
    )
    result = await session.stream(statement)
    values: list[str] = []
    async for row in result:
        runtime_ms = seconds_to_time_ms(row.time)
        values.append(
            "("
            + ",".join(
                (
                    str(row.steamid64 - STEAMID64_ACCOUNT_ID_BASE),
                    _mysql_string(row.map_name),
                    str(row.stage),
                    str(row.local_mode),
                    "0",
                    str(runtime_ms),
                    str(row.teleports),
                    _mysql_datetime(row.created_at),
                )
            )
            + ")"
        )
        if len(values) == SQL_VALUES_BATCH_SIZE:
            yield _times_insert(values)
            values = []
    if values:
        yield _times_insert(values)


def _times_insert(values: list[str]) -> str:
    return (
        "INSERT INTO `KztopImportTimes` "
        "(`SteamID32`,`MapName`,`Course`,`Mode`,`Style`,`RunTime`,`Teleports`,`Created`) VALUES\n"
        + ",\n".join(values)
        + ";\n"
    )


async def iter_gokz_localdb_mysql_sql(
    *,
    session: AsyncSession,
    server_ids: list[int],
    stats: GokzLocalDbExportStats,
) -> AsyncIterator[str]:
    server_id_list = ", ".join(str(server_id) for server_id in server_ids)
    yield (
        "-- GOKZ.TOP GOKZ LocalDB MySQL record export\n"
        f"-- GlobalAPI server IDs: {server_id_list}\n"
        f"-- Exported records: {stats.exportable_rows}\n"
        f"-- Skipped records: {stats.skipped_rows} "
        "(invalid or incompatible with GOKZ LocalDB)\n"
        "-- Import once into a GOKZ database whose LocalDB tables already exist.\n"
        "-- Existing Players and Maps are preserved; Times are appended.\n\n"
        "SET NAMES utf8mb4;\n"
        "SET time_zone = '+00:00';\n"
        "START TRANSACTION;\n\n"
    )
    async for chunk in _iter_players_sql(session=session, server_ids=server_ids):
        yield chunk
    yield "\n"
    async for chunk in _iter_maps_sql(session=session, server_ids=server_ids):
        yield chunk
    yield (
        "\nDROP TEMPORARY TABLE IF EXISTS `KztopImportTimes`;\n"
        "CREATE TEMPORARY TABLE `KztopImportTimes` (\n"
        "  `SteamID32` INTEGER UNSIGNED NOT NULL,\n"
        "  `MapName` VARCHAR(32) NOT NULL,\n"
        "  `Course` INTEGER UNSIGNED NOT NULL,\n"
        "  `Mode` TINYINT UNSIGNED NOT NULL,\n"
        "  `Style` TINYINT UNSIGNED NOT NULL,\n"
        "  `RunTime` INTEGER UNSIGNED NOT NULL,\n"
        "  `Teleports` SMALLINT UNSIGNED NOT NULL,\n"
        "  `Created` TIMESTAMP NOT NULL,\n"
        "  INDEX `IX_KztopImportTimes_MapCourse` (`MapName`,`Course`)\n"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;\n\n"
    )
    async for chunk in _iter_times_sql(session=session, server_ids=server_ids):
        yield chunk
    yield (
        "\nINSERT IGNORE INTO `MapCourses` (`MapID`,`Course`,`Created`)\n"
        "SELECT m.`MapID`, t.`Course`, MIN(t.`Created`)\n"
        "FROM `KztopImportTimes` t\n"
        "INNER JOIN `Maps` m ON m.`Name` = t.`MapName`\n"
        "GROUP BY m.`MapID`, t.`Course`;\n\n"
        "INSERT INTO `Times` "
        "(`SteamID32`,`MapCourseID`,`Mode`,`Style`,`RunTime`,`Teleports`,`Created`)\n"
        "SELECT t.`SteamID32`, mc.`MapCourseID`, t.`Mode`, t.`Style`, "
        "t.`RunTime`, t.`Teleports`, t.`Created`\n"
        "FROM `KztopImportTimes` t\n"
        "INNER JOIN `Maps` m ON m.`Name` = t.`MapName`\n"
        "INNER JOIN `MapCourses` mc "
        "ON mc.`MapID` = m.`MapID` AND mc.`Course` = t.`Course`;\n\n"
        "DROP TEMPORARY TABLE `KztopImportTimes`;\n"
        "COMMIT;\n"
    )


async def gzip_sql_stream(chunks: AsyncIterator[str]) -> AsyncIterator[bytes]:
    compressor = zlib.compressobj(level=6, method=zlib.DEFLATED, wbits=31)
    async for chunk in chunks:
        compressed = compressor.compress(chunk.encode("utf-8"))
        if compressed:
            yield compressed
    tail = compressor.flush()
    if tail:
        yield tail
