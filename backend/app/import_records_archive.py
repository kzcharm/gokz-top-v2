import argparse
import asyncio
import gzip
import json
import logging
import uuid
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, TextIO

from sqlalchemy import String, case, cast, or_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import select

from app import crud
from app.core.db import async_session_maker
from app.models import Map, Mode, Player, Record, ServerGlobalapi, generate_uuid7

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 5_000
DEFAULT_LOG_EVERY = 100_000
DEFAULT_CHUNK_SIZE = 1 << 20
POSTGRES_MAX_BIND_PARAMS = 65_535


@dataclass(frozen=True, slots=True)
class ImportArchiveResult:
    read: int = 0
    processed: int = 0
    created: int = 0
    updated: int = 0
    errors: int = 0


@dataclass(frozen=True, slots=True)
class ImportedRecordRow:
    id: int
    uuid: uuid.UUID
    steamid64: int
    player_name: str
    server_id: int
    server_name: str
    map_id: int
    map_name: str
    stage: int
    mode_id: int
    time_seconds: Decimal
    teleports: int
    points: int
    created_on: datetime
    updated_on: datetime
    updated_by: int
    replay_id: int | None
    is_valid: bool


def _iter_statement_chunks[T](items: Sequence[T], *, column_count: int) -> Iterator[list[T]]:
    if column_count <= 0:
        raise ValueError("column_count must be positive")
    max_rows = max(1, POSTGRES_MAX_BIND_PARAMS // column_count)
    for start in range(0, len(items), max_rows):
        yield list(items[start : start + max_rows])


def _normalize_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    raise ValueError("Invalid datetime payload")


def _parse_int(value: Any, *, field_name: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {field_name}") from exc


def _parse_string(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _parse_decimal(value: Any, *, field_name: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {field_name}") from exc


def _parse_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid optional integer field") from exc


def _parse_bool(value: Any, *, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1"}:
            return True
        if normalized in {"false", "0"}:
            return False
    raise ValueError(f"Invalid {field_name}")


def _open_text(path: Path) -> TextIO:
    if path.suffix == ".gz":
        return gzip.open(path, mode="rt", encoding="utf-8")
    return path.open(mode="rt", encoding="utf-8")


def _iter_json_array(stream: TextIO, *, chunk_size: int = DEFAULT_CHUNK_SIZE) -> Iterator[Any]:
    decoder = json.JSONDecoder()
    buffer = ""
    cursor = 0
    started = False
    finished = False
    expecting_item = False
    eof = False

    while True:
        if not eof and cursor >= len(buffer):
            chunk = stream.read(chunk_size)
            if chunk == "":
                eof = True
            else:
                buffer = chunk
                cursor = 0

        while True:
            while cursor < len(buffer) and buffer[cursor].isspace():
                cursor += 1

            if not started:
                if cursor >= len(buffer):
                    break
                if buffer[cursor] != "[":
                    raise ValueError("Expected a top-level JSON array")
                started = True
                expecting_item = True
                cursor += 1
                continue

            while cursor < len(buffer) and buffer[cursor].isspace():
                cursor += 1

            if cursor >= len(buffer):
                break

            if finished:
                if any(not char.isspace() for char in buffer[cursor:]):
                    raise ValueError("Unexpected trailing data after JSON array")
                cursor = len(buffer)
                break

            if buffer[cursor] == "]":
                finished = True
                cursor += 1
                continue

            if not expecting_item:
                if buffer[cursor] == ",":
                    expecting_item = True
                    cursor += 1
                    continue
                raise ValueError("Expected ',' or ']' after an array item")

            try:
                item, next_cursor = decoder.raw_decode(buffer, cursor)
            except json.JSONDecodeError as exc:
                if eof:
                    raise ValueError("Invalid JSON archive") from exc
                break

            yield item
            expecting_item = False
            cursor = next_cursor

        if eof:
            break

        if cursor > 0:
            buffer = buffer[cursor:]
            cursor = 0

        chunk = stream.read(chunk_size)
        if chunk == "":
            eof = True
        else:
            buffer += chunk

    if not started:
        raise ValueError("Archive does not contain JSON data")
    if not finished:
        raise ValueError("Archive ended before the JSON array was closed")
    if buffer[cursor:].strip():
        raise ValueError("Unexpected trailing data after JSON array")


def iter_record_payloads(path: Path) -> Iterator[dict[str, Any]]:
    with _open_text(path) as stream:
        for item in _iter_json_array(stream):
            if not isinstance(item, dict):
                raise ValueError("Expected every array item to be a JSON object")
            yield item


def _normalize_record_payload(
    *,
    payload: dict[str, Any],
    mode_ids_by_name: dict[str, int],
) -> ImportedRecordRow:
    raw_record_id = payload.get("id")
    if raw_record_id is None:
        raise ValueError("Record id is required for upsert")
    record_id = _parse_int(raw_record_id, field_name="id")
    steamid64 = _parse_int(payload.get("steamid64"), field_name="steamid64")
    server_id = _parse_int(payload.get("server_id"), field_name="server_id")
    map_id = _parse_int(payload.get("map_id"), field_name="map_id")
    stage = _parse_int(payload.get("stage", 0), field_name="stage")
    if stage < 0:
        raise ValueError("Stage must be non-negative")

    teleports = _parse_int(payload.get("teleports", 0), field_name="teleports")
    if teleports < 0:
        raise ValueError("Teleports must be non-negative")

    points = _parse_int(payload.get("points", 0), field_name="points")
    if not 0 <= points <= 1000:
        raise ValueError("Points out of range")

    mode_name = _parse_string(payload.get("mode"))
    mode_id = mode_ids_by_name.get(mode_name)
    if mode_id is None:
        raise ValueError(f"Unknown mode {mode_name!r}")

    created_on = _normalize_datetime(payload.get("created_on"))
    updated_on = _normalize_datetime(payload.get("updated_on"))

    return ImportedRecordRow(
        id=record_id,
        uuid=generate_uuid7(timestamp=created_on),
        steamid64=steamid64,
        player_name=_parse_string(payload.get("player_name")) or str(steamid64),
        server_id=server_id,
        server_name=_parse_string(payload.get("server_name")) or f"server_{server_id}",
        map_id=map_id,
        map_name=_parse_string(payload.get("map_name")) or f"map_{map_id}",
        stage=stage,
        mode_id=mode_id,
        time_seconds=_parse_decimal(payload.get("time"), field_name="time"),
        teleports=teleports,
        points=points,
        created_on=created_on,
        updated_on=updated_on,
        updated_by=_parse_int(payload.get("updated_by", 0), field_name="updated_by"),
        replay_id=_parse_optional_int(payload.get("replay_id")),
        is_valid=_parse_bool(payload.get("is_valid", True), field_name="is_valid"),
    )


async def _load_mode_ids_by_name() -> dict[str, int]:
    async with async_session_maker() as session:
        await crud.sync_canonical_modes(session=session)
        statement = select(Mode)
        modes = list((await session.exec(statement)).all())
    return {mode.name: mode.id for mode in modes}


async def _upsert_players(*, session, rows: list[ImportedRecordRow]) -> None:
    now = datetime.now(UTC)
    players_by_id: dict[int, dict[str, Any]] = {}
    for row in rows:
        existing = players_by_id.get(row.steamid64)
        if existing is None:
            players_by_id[row.steamid64] = {
                "steamid64": row.steamid64,
                "name": row.player_name,
                "created_at": row.created_on,
                "last_played_at": row.created_on,
                "updated_at": now,
            }
            continue
        if row.created_on < existing["created_at"]:
            existing["created_at"] = row.created_on
        if row.created_on > existing["last_played_at"]:
            existing["last_played_at"] = row.created_on
        if row.player_name:
            existing["name"] = row.player_name

    player_values = list(players_by_id.values())
    for player_chunk in _iter_statement_chunks(player_values, column_count=5):
        insert_stmt = pg_insert(Player).values(player_chunk)
        await session.exec(
            insert_stmt.on_conflict_do_update(
                index_elements=[Player.steamid64],
                set_={
                    "name": case(
                        (
                            or_(
                                Player.name.is_(None),
                                Player.name == "",
                                Player.name == cast(Player.steamid64, String()),
                            ),
                            insert_stmt.excluded.name,
                        ),
                        else_=Player.name,
                    ),
                    "created_at": case(
                        (Player.created_at.is_(None), insert_stmt.excluded.created_at),
                        (
                            Player.created_at > insert_stmt.excluded.created_at,
                            insert_stmt.excluded.created_at,
                        ),
                        else_=Player.created_at,
                    ),
                    "last_played_at": case(
                        (
                            Player.last_played_at.is_(None),
                            insert_stmt.excluded.last_played_at,
                        ),
                        (
                            Player.last_played_at < insert_stmt.excluded.last_played_at,
                            insert_stmt.excluded.last_played_at,
                        ),
                        else_=Player.last_played_at,
                    ),
                    "updated_at": insert_stmt.excluded.updated_at,
                },
            )
        )


async def _upsert_maps(*, session, rows: list[ImportedRecordRow]) -> None:
    maps_by_id: dict[int, dict[str, Any]] = {}
    now = datetime.now(UTC)
    for row in rows:
        maps_by_id.setdefault(
            row.map_id,
            {
                "id": row.map_id,
                "name": row.map_name,
                "filesize": 0,
                "validated": False,
                "difficulty": 0,
                "created_on": now,
                "updated_on": now,
                "approved_by_steamid64": 0,
                "synced_at": now,
            },
        )

    map_values = list(maps_by_id.values())
    for map_chunk in _iter_statement_chunks(map_values, column_count=9):
        insert_stmt = pg_insert(Map).values(map_chunk)
        await session.exec(insert_stmt.on_conflict_do_nothing(index_elements=[Map.id]))


async def _upsert_servers(*, session, rows: list[ImportedRecordRow]) -> None:
    servers_by_id: dict[int, dict[str, Any]] = {}
    now = datetime.now(UTC)
    for row in rows:
        servers_by_id.setdefault(
            row.server_id,
            {
                "id": row.server_id,
                "port": 27015,
                "ip": None,
                "name": row.server_name,
                "owner_steamid64": 0,
                "approval_status": 0,
                "approved_by_steamid64": 0,
                "created_on": now,
                "updated_on": now,
                "synced_at": now,
            },
        )

    server_values = list(servers_by_id.values())
    for server_chunk in _iter_statement_chunks(server_values, column_count=10):
        insert_stmt = pg_insert(ServerGlobalapi).values(server_chunk)
        await session.exec(
            insert_stmt.on_conflict_do_nothing(index_elements=[ServerGlobalapi.id])
        )


async def _upsert_records(*, session, rows: list[ImportedRecordRow]) -> tuple[int, int]:
    record_ids = [row.id for row in rows]
    existing_ids = set(
        (
            await session.exec(select(Record.id).where(Record.id.in_(record_ids)))
        ).all()
    )

    record_values = [
        {
            "uuid": row.uuid,
            "id": row.id,
            "steamid64": row.steamid64,
            "server_id": row.server_id,
            "mode_id": row.mode_id,
            "map_id": row.map_id,
            "stage": row.stage,
            "time": row.time_seconds,
            "teleports": row.teleports,
            "points": row.points,
            "created_on": row.created_on,
            "updated_on": row.updated_on,
            "updated_by": row.updated_by,
            "replay_id": row.replay_id,
            "is_valid": row.is_valid,
        }
        for row in rows
    ]
    for record_chunk in _iter_statement_chunks(record_values, column_count=15):
        insert_stmt = pg_insert(Record).values(record_chunk)
        await session.exec(
            insert_stmt.on_conflict_do_update(
                index_elements=[Record.id],
                index_where=Record.id.is_not(None),
                set_={
                    "steamid64": insert_stmt.excluded.steamid64,
                    "server_id": insert_stmt.excluded.server_id,
                    "mode_id": insert_stmt.excluded.mode_id,
                    "map_id": insert_stmt.excluded.map_id,
                    "stage": insert_stmt.excluded.stage,
                    "time": insert_stmt.excluded.time,
                    "teleports": insert_stmt.excluded.teleports,
                    "points": insert_stmt.excluded.points,
                    "created_on": insert_stmt.excluded.created_on,
                    "updated_on": insert_stmt.excluded.updated_on,
                    "updated_by": insert_stmt.excluded.updated_by,
                    "replay_id": insert_stmt.excluded.replay_id,
                    "is_valid": insert_stmt.excluded.is_valid,
                },
            )
        )
    updated = len(existing_ids)
    created = len(rows) - updated
    return created, updated


async def _import_batch(*, session, rows: list[ImportedRecordRow]) -> tuple[int, int]:
    await _upsert_players(session=session, rows=rows)
    await _upsert_maps(session=session, rows=rows)
    await _upsert_servers(session=session, rows=rows)
    created, updated = await _upsert_records(session=session, rows=rows)
    await session.commit()
    return created, updated


async def import_records_from_path(
    path: Path,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    log_every: int = DEFAULT_LOG_EVERY,
    limit: int | None = None,
) -> ImportArchiveResult:
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    if log_every <= 0:
        raise ValueError("log_every must be positive")

    mode_ids_by_name = await _load_mode_ids_by_name()
    read = 0
    processed = 0
    created = 0
    updated = 0
    errors = 0
    pending_rows: list[ImportedRecordRow] = []

    async with async_session_maker() as session:
        for payload in iter_record_payloads(path):
            read += 1
            if limit is not None and read > limit:
                break

            try:
                row = _normalize_record_payload(
                    payload=payload,
                    mode_ids_by_name=mode_ids_by_name,
                )
            except ValueError as exc:
                errors += 1
                logger.warning("Skipping record %r: %s", payload.get("id"), exc)
                continue

            pending_rows.append(row)
            if len(pending_rows) < batch_size:
                if read % log_every == 0:
                    logger.info(
                        "Read %s records from %s so far",
                        f"{read:,}",
                        path,
                    )
                continue

            batch_created, batch_updated = await _import_batch(
                session=session,
                rows=pending_rows,
            )
            processed += len(pending_rows)
            created += batch_created
            updated += batch_updated
            pending_rows = []

            if read % log_every == 0:
                logger.info(
                    "Imported %s records from %s so far",
                    f"{processed:,}",
                    path,
                )

        if pending_rows:
            batch_created, batch_updated = await _import_batch(
                session=session,
                rows=pending_rows,
            )
            processed += len(pending_rows)
            created += batch_created
            updated += batch_updated

    return ImportArchiveResult(
        read=read,
        processed=processed,
        created=created,
        updated=updated,
        errors=errors,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Import GlobalAPI-like records from a JSON or JSON.GZ archive",
    )
    parser.add_argument("path", type=Path, help="Path to the JSON or JSON.GZ archive")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Number of records to write per transaction (default: {DEFAULT_BATCH_SIZE})",
    )
    parser.add_argument(
        "--log-every",
        type=int,
        default=DEFAULT_LOG_EVERY,
        help=f"Log progress every N records read (default: {DEFAULT_LOG_EVERY})",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Stop after reading at most this many records",
    )
    return parser


async def _main_async(argv: Sequence[str] | None = None) -> ImportArchiveResult:
    args = _build_parser().parse_args(argv)
    result = await import_records_from_path(
        args.path,
        batch_size=args.batch_size,
        log_every=args.log_every,
        limit=args.limit,
    )
    logger.info(
        "Import finished: read=%s processed=%s created=%s updated=%s errors=%s",
        f"{result.read:,}",
        f"{result.processed:,}",
        f"{result.created:,}",
        f"{result.updated:,}",
        f"{result.errors:,}",
    )
    return result


def main(argv: Sequence[str] | None = None) -> None:
    asyncio.run(_main_async(argv))


if __name__ == "__main__":
    main()
