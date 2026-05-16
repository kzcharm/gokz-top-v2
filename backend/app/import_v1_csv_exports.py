import argparse
import asyncio
import csv
import json
import logging
import uuid
from collections.abc import Iterable, Iterator, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import select

from app.core.db import async_session_maker
from app.crud.map_review import rebuild_map_review_summary
from app.models import (
    Map,
    MapReview,
    MapReviewCommentInput,
    MapReviewContentInput,
    Player,
    PlayerSession,
    ServerGroup,
    ServerGroupStatus,
    generate_uuid7,
)
from app.services.language_detection import detect_language_code

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 5_000


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Import gokztop v1 player_sessions.csv and map_review.csv into v2.",
    )
    parser.add_argument(
        "--player-sessions-csv",
        type=Path,
        required=True,
        help="Path to the gokztop v1 player_sessions.csv export.",
    )
    parser.add_argument(
        "--map-review-csv",
        type=Path,
        required=True,
        help="Path to the gokztop v1 map_review.csv export.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="Maximum player_session rows to upsert per transaction.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Inspect the CSVs and database dependencies without writing rows.",
    )
    return parser


def _chunked[T](items: Sequence[T], *, size: int) -> Iterator[Sequence[T]]:
    if size < 1:
        raise ValueError("chunk size must be at least 1")
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _normalize_datetime(raw_value: str, *, field_name: str) -> datetime:
    normalized = raw_value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")

    parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _normalize_optional_datetime(raw_value: str) -> datetime | None:
    normalized = raw_value.strip()
    if not normalized:
        return None
    return _normalize_datetime(normalized, field_name="datetime")


def _normalize_uuid(raw_value: str, *, field_name: str) -> uuid.UUID:
    normalized = raw_value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return uuid.UUID(normalized)


def _normalize_int(raw_value: str, *, field_name: str) -> int:
    normalized = raw_value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return int(normalized)


def _normalize_optional_int(raw_value: Any, *, field_name: str) -> int | None:
    if raw_value is None:
        return None
    normalized = str(raw_value).strip()
    if not normalized:
        return None
    return _normalize_int(normalized, field_name=field_name)


def _normalize_text(raw_value: str, *, field_name: str) -> str:
    normalized = raw_value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


def _normalize_session_timestamps(
    *,
    connected_at: datetime,
    disconnect_at: datetime | None,
) -> tuple[datetime | None, datetime, bool]:
    if disconnect_at is None:
        return None, connected_at, False
    if disconnect_at < connected_at:
        return connected_at, connected_at, True
    return disconnect_at, disconnect_at, False


def _read_player_session_dependencies(path: Path) -> tuple[set[int], set[uuid.UUID], int]:
    player_ids: set[int] = set()
    group_ids: set[uuid.UUID] = set()
    row_count = 0

    with path.open(newline="", encoding="utf-8-sig") as stream:
        for row in csv.DictReader(stream):
            row_count += 1
            player_ids.add(
                _normalize_int(row["player_steamid64"], field_name="player_steamid64")
            )
            group_ids.add(_normalize_uuid(row["server_group_id"], field_name="server_group_id"))

    return player_ids, group_ids, row_count


def _read_map_review_rows(path: Path) -> tuple[list[dict[str, Any]], set[int], set[int]]:
    rows: list[dict[str, Any]] = []
    player_ids: set[int] = set()
    map_ids: set[int] = set()

    with path.open(newline="", encoding="utf-8-sig") as stream:
        for row in csv.DictReader(stream):
            rows.append(row)
            player_ids.add(_normalize_int(row["steamid64"], field_name="steamid64"))
            map_ids.add(_normalize_int(row["map_id"], field_name="map_id"))

    return rows, player_ids, map_ids


def _build_placeholder_server_group_rows(
    group_ids: Iterable[uuid.UUID],
) -> list[dict[str, Any]]:
    now = datetime.now(UTC)
    rows: list[dict[str, Any]] = []
    for group_id in sorted(group_ids, key=str):
        rows.append(
            {
                "id": group_id,
                "name": f"Imported v1 server group {str(group_id)[:8]}",
                "api_key": str(group_id),
                "status": ServerGroupStatus.PENDING,
                "created_at": now,
                "updated_at": now,
            }
        )
    return rows


def _build_placeholder_player_rows(player_ids: Iterable[int]) -> list[dict[str, Any]]:
    now = datetime.now(UTC)
    rows: list[dict[str, Any]] = []
    for steamid64 in sorted(player_ids):
        rows.append(
            {
                "steamid64": steamid64,
                "name": str(steamid64),
                "created_at": now,
                "updated_at": now,
            }
        )
    return rows


def _normalize_review_comment_text(raw_comment: Any) -> str | None:
    if isinstance(raw_comment, dict):
        candidate = raw_comment.get("text")
    else:
        candidate = raw_comment

    if candidate is None:
        return None
    candidate_text = str(candidate)
    if len(candidate_text) > 1000:
        candidate_text = candidate_text[:1000]
    return MapReviewCommentInput(text=candidate_text).text


def _normalize_review_content(
    *,
    raw_content: str,
    created_at: datetime,
    updated_at: datetime,
) -> dict[str, Any]:
    payload = json.loads(raw_content)
    if not isinstance(payload, dict):
        raise ValueError("map review content must be a JSON object")

    comment_text = _normalize_review_comment_text(payload.get("comment"))
    content_input = MapReviewContentInput(
        overall=_normalize_int(str(payload["overall"]), field_name="overall"),
        gameplay=_normalize_optional_int(payload.get("gameplay"), field_name="gameplay"),
        visuals=_normalize_optional_int(payload.get("visuals"), field_name="visuals"),
        comment=MapReviewCommentInput(text=comment_text),
    )

    normalized: dict[str, Any] = {
        "overall": content_input.overall,
        "gameplay": content_input.gameplay,
        "visuals": content_input.visuals,
    }
    if content_input.comment is None or content_input.comment.text is None:
        normalized["comment"] = None
        return normalized

    language = payload.get("lang")
    if not isinstance(language, str) or not language.strip():
        language = detect_language_code(content_input.comment.text)

    normalized["comment"] = {
        "text": content_input.comment.text,
        "language": language,
        "created_at": created_at.isoformat(),
        "updated_at": updated_at.isoformat(),
    }
    return normalized


def _iter_player_session_batches(
    path: Path,
    *,
    batch_size: int,
) -> Iterator[tuple[list[dict[str, Any]], int]]:
    batch: list[dict[str, Any]] = []
    clamped_in_batch = 0
    with path.open(newline="", encoding="utf-8-sig") as stream:
        for row in csv.DictReader(stream):
            connected_at = _normalize_datetime(
                row["connected_time"],
                field_name="connected_time",
            )
            disconnect_at, last_heartbeat_at, was_clamped = _normalize_session_timestamps(
                connected_at=connected_at,
                disconnect_at=_normalize_optional_datetime(row["disconnect_time"]),
            )
            if was_clamped:
                clamped_in_batch += 1

            batch.append(
                {
                    "id": _normalize_uuid(row["id"], field_name="id"),
                    "player_steamid64": _normalize_int(
                        row["player_steamid64"],
                        field_name="player_steamid64",
                    ),
                    "server_group_id": _normalize_uuid(
                        row["server_group_id"],
                        field_name="server_group_id",
                    ),
                    "connected_at": connected_at,
                    "disconnect_at": disconnect_at,
                    "last_heartbeat_at": last_heartbeat_at,
                    "ip_address": _normalize_text(row["ip_address"], field_name="ip_address"),
                    "map_name": _normalize_text(row["map_name"], field_name="map_name"),
                }
            )
            if len(batch) >= batch_size:
                yield batch, clamped_in_batch
                batch = []
                clamped_in_batch = 0

    if batch:
        yield batch, clamped_in_batch


def _build_map_review_rows(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized_rows: list[dict[str, Any]] = []
    for row in rows:
        created_at = _normalize_datetime(row["created_at"], field_name="created_at")
        updated_at = _normalize_datetime(row["updated_at"], field_name="updated_at")
        normalized_rows.append(
            {
                "id": generate_uuid7(timestamp=updated_at),
                "steamid64": _normalize_int(row["steamid64"], field_name="steamid64"),
                "map_id": _normalize_int(row["map_id"], field_name="map_id"),
                "server_group_id": None,
                "content": _normalize_review_content(
                    raw_content=row["content"],
                    created_at=created_at,
                    updated_at=updated_at,
                ),
                "created_at": created_at,
                "updated_at": updated_at,
            }
        )
    return normalized_rows


async def _insert_placeholder_players(*, player_ids: set[int]) -> int:
    if not player_ids:
        return 0

    async with async_session_maker() as session:
        existing_player_ids = set(
            (
                await session.exec(
                    select(Player.steamid64).where(Player.steamid64.in_(player_ids))
                )
            ).all()
        )
        missing_player_ids = player_ids - existing_player_ids
        if not missing_player_ids:
            return 0

        rows = _build_placeholder_player_rows(missing_player_ids)
        for chunk in _chunked(rows, size=1_000):
            statement = pg_insert(Player.__table__).values(list(chunk)).on_conflict_do_nothing(
                index_elements=[Player.__table__.c.steamid64]
            )
            await session.exec(statement)
        await session.commit()
        return len(rows)


async def _insert_placeholder_server_groups(*, group_ids: set[uuid.UUID]) -> int:
    if not group_ids:
        return 0

    async with async_session_maker() as session:
        existing_group_ids = set(
            (await session.exec(select(ServerGroup.id).where(ServerGroup.id.in_(group_ids)))).all()
        )
        missing_group_ids = group_ids - existing_group_ids
        if not missing_group_ids:
            return 0

        rows = _build_placeholder_server_group_rows(missing_group_ids)
        statement = pg_insert(ServerGroup.__table__).values(rows).on_conflict_do_nothing(
            index_elements=[ServerGroup.__table__.c.id]
        )
        await session.exec(statement)
        await session.commit()
        return len(rows)


async def _assert_review_maps_exist(*, map_ids: set[int]) -> None:
    if not map_ids:
        return

    async with async_session_maker() as session:
        existing_map_ids = set((await session.exec(select(Map.id).where(Map.id.in_(map_ids)))).all())
    missing_map_ids = map_ids - existing_map_ids
    if missing_map_ids:
        missing_ids = ", ".join(str(map_id) for map_id in sorted(missing_map_ids))
        raise ValueError(f"map_review.csv references missing map ids: {missing_ids}")


async def _import_player_sessions(*, path: Path, batch_size: int) -> tuple[int, int]:
    inserted_rows = 0
    clamped_rows = 0
    async with async_session_maker() as session:
        for batch, clamped_in_batch in _iter_player_session_batches(path, batch_size=batch_size):
            statement = pg_insert(PlayerSession.__table__).values(batch).on_conflict_do_update(
                index_elements=[PlayerSession.__table__.c.id],
                set_={
                    "player_steamid64": statement_excluded(PlayerSession, "player_steamid64"),
                    "server_group_id": statement_excluded(PlayerSession, "server_group_id"),
                    "connected_at": statement_excluded(PlayerSession, "connected_at"),
                    "disconnect_at": statement_excluded(PlayerSession, "disconnect_at"),
                    "last_heartbeat_at": statement_excluded(PlayerSession, "last_heartbeat_at"),
                    "ip_address": statement_excluded(PlayerSession, "ip_address"),
                    "map_name": statement_excluded(PlayerSession, "map_name"),
                },
            )
            await session.exec(statement)
            await session.commit()
            inserted_rows += len(batch)
            clamped_rows += clamped_in_batch
            logger.info("Upserted %s player_session rows so far", inserted_rows)
    return inserted_rows, clamped_rows


async def _import_map_reviews(*, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0

    normalized_rows = _build_map_review_rows(rows)
    touched_map_ids = {row["map_id"] for row in normalized_rows}

    async with async_session_maker() as session:
        for chunk in _chunked(normalized_rows, size=500):
            statement = pg_insert(MapReview.__table__).values(list(chunk)).on_conflict_do_update(
                constraint="uq_map_review_context",
                set_={
                    "content": statement_excluded(MapReview, "content"),
                    "created_at": statement_excluded(MapReview, "created_at"),
                    "updated_at": statement_excluded(MapReview, "updated_at"),
                },
            )
            await session.exec(statement)

        for map_id in sorted(touched_map_ids):
            await rebuild_map_review_summary(session=session, map_id=map_id)

        await session.commit()
    return len(normalized_rows)


def statement_excluded(model: type[Any], column_name: str) -> Any:
    return pg_insert(model.__table__).excluded[column_name]


async def _main_async(argv: list[str] | None = None) -> None:
    args = _build_parser().parse_args(argv)
    if args.batch_size < 1:
        raise ValueError("--batch-size must be at least 1")

    player_sessions_csv = args.player_sessions_csv.resolve()
    map_review_csv = args.map_review_csv.resolve()
    if not player_sessions_csv.is_file():
        raise FileNotFoundError(player_sessions_csv)
    if not map_review_csv.is_file():
        raise FileNotFoundError(map_review_csv)

    session_player_ids, session_group_ids, session_row_count = _read_player_session_dependencies(
        player_sessions_csv
    )
    map_review_rows, review_player_ids, review_map_ids = _read_map_review_rows(map_review_csv)

    async with async_session_maker() as session:
        existing_player_ids = set(
            (
                await session.exec(
                    select(Player.steamid64).where(
                        Player.steamid64.in_(session_player_ids | review_player_ids)
                    )
                )
            ).all()
        )
        existing_group_ids = set(
            (
                await session.exec(
                    select(ServerGroup.id).where(ServerGroup.id.in_(session_group_ids))
                )
            ).all()
        )
        existing_map_ids = set(
            (await session.exec(select(Map.id).where(Map.id.in_(review_map_ids)))).all()
        )

    logger.info("player_sessions.csv rows: %s", session_row_count)
    logger.info("map_review.csv rows: %s", len(map_review_rows))
    logger.info(
        "Missing placeholder players needed: %s",
        len((session_player_ids | review_player_ids) - existing_player_ids),
    )
    logger.info(
        "Missing placeholder server groups needed: %s",
        len(session_group_ids - existing_group_ids),
    )
    logger.info(
        "Missing review map ids: %s",
        len(review_map_ids - existing_map_ids),
    )

    if args.dry_run:
        return

    placeholder_players = await _insert_placeholder_players(
        player_ids=session_player_ids | review_player_ids
    )
    placeholder_groups = await _insert_placeholder_server_groups(group_ids=session_group_ids)
    await _assert_review_maps_exist(map_ids=review_map_ids)
    imported_sessions, clamped_sessions = await _import_player_sessions(
        path=player_sessions_csv,
        batch_size=args.batch_size,
    )
    imported_reviews = await _import_map_reviews(rows=map_review_rows)

    logger.info("Inserted placeholder players: %s", placeholder_players)
    logger.info("Inserted placeholder server groups: %s", placeholder_groups)
    logger.info("Upserted player sessions: %s", imported_sessions)
    logger.info("Clamped invalid legacy session end-times: %s", clamped_sessions)
    logger.info("Upserted map reviews: %s", imported_reviews)


def main(argv: list[str] | None = None) -> None:
    asyncio.run(_main_async(argv))


if __name__ == "__main__":
    main()
