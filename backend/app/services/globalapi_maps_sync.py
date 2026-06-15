import re
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models import KZMode, Map, MapCourse, MapCourseTier, MapSyncResult
from app.services.map_authors import (
    ensure_author_players_exist,
    merge_author_fields,
    normalize_author_fields,
)
from app.services.steam_workshop import fetch_workshop_file_details

GLOBALAPI_MAPS_LIMIT = 9999
MAP_DATETIME_FALLBACK = "2018-01-09T10:45:50"
_MAP_DATETIME_FALLBACK_VALUE = datetime.fromisoformat(MAP_DATETIME_FALLBACK).replace(
    tzinfo=UTC
)
_WORKSHOP_ID_PATTERN = re.compile(r"[?&]id=(\d+)")
_MAP_DIFFICULTY_TIER_MODES = (KZMode.KZT, KZMode.SKZ)


class GlobalAPIMapsSyncError(RuntimeError):
    pass


def _normalize_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.year < 1900:
            return _MAP_DATETIME_FALLBACK_VALUE
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.year < 1900:
                return _MAP_DATETIME_FALLBACK_VALUE
            return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
        except ValueError:
            return _MAP_DATETIME_FALLBACK_VALUE

    return _MAP_DATETIME_FALLBACK_VALUE


def _parse_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
    return default


def _extract_workshop_id(workshop_url: Any) -> int | None:
    if not workshop_url or not isinstance(workshop_url, str):
        return None

    match = _WORKSHOP_ID_PATTERN.search(workshop_url)
    if match:
        return _parse_int(match.group(1), default=0) or None

    stripped = workshop_url.strip()
    if stripped.isdigit():
        parsed = _parse_int(stripped, default=0)
        return parsed or None

    return None


def _map_values_from_globalapi(payload: dict[str, Any]) -> dict[str, Any]:
    authors, no_steamid_names = normalize_author_fields(
        authors=payload.get("authors"),
        no_steamid_names=payload.get("no_steamid_names"),
    )
    return {
        "name": str(payload.get("name") or ""),
        "filesize": _parse_int(payload.get("filesize"), default=0),
        "validated": _parse_bool(payload.get("validated", False), default=False),
        "difficulty": _parse_int(payload.get("difficulty"), default=0),
        "created_at": _normalize_datetime(payload.get("created_on")),
        "updated_at": _normalize_datetime(payload.get("updated_on")),
        "approved_by_steamid64": _parse_int(
            payload.get("approved_by_steamid64"), default=0
        ),
        "workshop_id": _extract_workshop_id(payload.get("workshop_url")),
        "authors": authors,
        "no_steamid_names": no_steamid_names,
    }


async def _fetch_workshop_author_ids_by_map_id(
    *,
    map_rows_by_id: dict[int, dict[str, Any]],
) -> dict[int, list[str]]:
    workshop_ids_by_map_id = {
        map_id: str(row["workshop_id"])
        for map_id, row in map_rows_by_id.items()
        if row.get("workshop_id") is not None
    }
    if not workshop_ids_by_map_id:
        return {}

    details_by_workshop_id = await fetch_workshop_file_details(
        workshop_ids=list(workshop_ids_by_map_id.values()),
    )
    author_ids_by_map_id: dict[int, list[str]] = {}
    for map_id, workshop_id in workshop_ids_by_map_id.items():
        details = details_by_workshop_id.get(workshop_id)
        if details is None or details.creator is None:
            continue
        author_ids_by_map_id[map_id] = [details.creator]
    return author_ids_by_map_id


async def fetch_maps_from_globalapi() -> list[dict[str, Any]]:
    try:
        async with httpx.AsyncClient(
            timeout=settings.GLOBALAPI_TIMEOUT_SECONDS,
            trust_env=settings.GLOBALAPI_HTTPX_TRUST_ENV,
        ) as client:
            response = await client.get(
                f"{settings.GLOBALAPI_BASE_URL}/maps",
                params={"limit": GLOBALAPI_MAPS_LIMIT},
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise GlobalAPIMapsSyncError("Failed to fetch maps from GlobalAPI") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise GlobalAPIMapsSyncError("GlobalAPI returned invalid map payload") from exc

    if not isinstance(payload, list):
        raise GlobalAPIMapsSyncError("GlobalAPI returned unexpected map payload type")

    return [item for item in payload if isinstance(item, dict)]


async def _mark_missing_maps_invalid(
    *,
    session: AsyncSession,
    upstream_ids: set[int],
    synced_at: datetime,
) -> int:
    missing_rows = list(
        (
            await session.exec(
                select(Map).where(
                    col(Map.id) > 0,
                    col(Map.id).not_in(upstream_ids),
                    col(Map.validated).is_(True),
                )
            )
        ).all()
    )
    for map_obj in missing_rows:
        map_obj.validated = False
        map_obj.synced_at = synced_at
        session.add(map_obj)
    await session.flush()
    return len(missing_rows)


async def _sync_main_course_tiers_from_map_difficulty(
    *,
    session: AsyncSession,
    synced_map_ids: set[int],
    difficulty_changed_map_ids: set[int],
) -> None:
    if not synced_map_ids:
        return

    main_courses = list(
        (
            await session.exec(
                select(MapCourse, Map)
                .join(Map, col(Map.id) == col(MapCourse.map_id))
                .where(
                    col(MapCourse.map_id).in_(synced_map_ids),
                    col(MapCourse.stage) == 0,
                    col(Map.id) > 0,
                )
            )
        ).all()
    )
    if not main_courses:
        return

    course_ids = [course.id for course, _map_obj in main_courses if course.id is not None]
    if not course_ids:
        return

    existing_tier_keys = {
        (course_id, mode)
        for course_id, mode in (
            await session.exec(
                select(MapCourseTier.course_id, MapCourseTier.mode).where(
                    col(MapCourseTier.course_id).in_(course_ids),
                    col(MapCourseTier.mode).in_(list(_MAP_DIFFICULTY_TIER_MODES)),
                )
            )
        ).all()
    }

    now = datetime.now(UTC)
    rows_to_upsert: list[dict[str, Any]] = []
    for course, map_obj in main_courses:
        if course.id is None:
            continue
        difficulty_changed = map_obj.id in difficulty_changed_map_ids
        for mode in _MAP_DIFFICULTY_TIER_MODES:
            if (course.id, mode) in existing_tier_keys and not difficulty_changed:
                continue
            rows_to_upsert.append(
                {
                    "course_id": course.id,
                    "mode": mode,
                    "tier": map_obj.difficulty,
                    "created_at": now,
                    "updated_at": now,
                    "updated_by_id": "globalapi-map-sync",
                }
            )

    if not rows_to_upsert:
        return

    table = MapCourseTier.__table__  # type: ignore[attr-defined]
    insert_statement = pg_insert(table).values(rows_to_upsert)
    await session.exec(
        insert_statement.on_conflict_do_update(
            index_elements=[table.c.course_id, table.c.mode],
            set_={
                "tier": insert_statement.excluded.tier,
                "updated_at": insert_statement.excluded.updated_at,
                "updated_by_id": insert_statement.excluded.updated_by_id,
            },
        )
    )


async def sync_maps_from_globalapi(*, session: AsyncSession) -> MapSyncResult:
    maps_data = await fetch_maps_from_globalapi()

    now = datetime.now(UTC)
    map_rows_by_id: dict[int, dict[str, Any]] = {}
    errors = 0

    for map_payload in maps_data:
        map_id = _parse_int(map_payload.get("id"), default=-1)
        if map_id < 0:
            errors += 1
            continue

        map_rows_by_id[map_id] = {
            "id": map_id,
            **_map_values_from_globalapi(map_payload),
            "synced_at": now,
        }

    if not map_rows_by_id:
        return MapSyncResult(
            processed=len(maps_data),
            created=0,
            updated=0,
            errors=errors,
        )

    map_ids = list(map_rows_by_id.keys())
    workshop_author_ids_by_map_id = await _fetch_workshop_author_ids_by_map_id(
        map_rows_by_id=map_rows_by_id,
    )
    existing_rows = list(
        (
            await session.exec(
                select(
                    Map.id,
                    Map.difficulty,
                    Map.authors,
                    Map.no_steamid_names,
                ).where(col(Map.id).in_(map_ids))
            )
        ).all()
    )
    existing_difficulty_by_id = {
        int(map_id): int(difficulty)
        for map_id, difficulty, _authors, _names in existing_rows
    }
    existing_author_fields_by_id = {
        int(map_id): (authors, no_steamid_names)
        for map_id, _difficulty, authors, no_steamid_names in existing_rows
    }
    existing_ids = set(existing_difficulty_by_id)
    created = sum(1 for map_id in map_ids if map_id not in existing_ids)
    updated = len(map_ids) - created
    difficulty_changed_map_ids = {
        map_id
        for map_id, row in map_rows_by_id.items()
        if map_id in existing_difficulty_by_id
        and existing_difficulty_by_id[map_id] != row["difficulty"]
    }
    for map_id, row in map_rows_by_id.items():
        existing_authors, existing_no_steamid_names = existing_author_fields_by_id.get(
            map_id,
            ([], []),
        )
        merged_authors, merged_no_steamid_names = merge_author_fields(
            existing_authors=existing_authors,
            existing_no_steamid_names=existing_no_steamid_names,
            incoming_authors=[
                *list(row.get("authors") or []),
                *workshop_author_ids_by_map_id.get(map_id, []),
            ],
            incoming_no_steamid_names=row.get("no_steamid_names"),
        )
        row["authors"] = merged_authors
        row["no_steamid_names"] = merged_no_steamid_names
    await ensure_author_players_exist(
        session=session,
        author_steamid64s=[
            author
            for row in map_rows_by_id.values()
            for author in list(row.get("authors") or [])
        ],
    )

    map_table = Map.__table__  # type: ignore[attr-defined]
    rows_to_upsert = list(map_rows_by_id.values())
    insert_statement = pg_insert(map_table).values(rows_to_upsert)
    upsert_statement = insert_statement.on_conflict_do_update(
        index_elements=[map_table.c.id],
        set_={
            "name": insert_statement.excluded.name,
            "filesize": insert_statement.excluded.filesize,
            "validated": insert_statement.excluded.validated,
            "difficulty": insert_statement.excluded.difficulty,
            "created_at": insert_statement.excluded.created_at,
            "updated_at": insert_statement.excluded.updated_at,
            "approved_by_steamid64": insert_statement.excluded.approved_by_steamid64,
            "workshop_id": insert_statement.excluded.workshop_id,
            "authors": insert_statement.excluded.authors,
            "no_steamid_names": insert_statement.excluded.no_steamid_names,
            "synced_at": insert_statement.excluded.synced_at,
        },
    )
    await session.exec(upsert_statement)
    updated += await _mark_missing_maps_invalid(
        session=session,
        upstream_ids=set(map_ids),
        synced_at=now,
    )
    await _sync_main_course_tiers_from_map_difficulty(
        session=session,
        synced_map_ids=set(map_ids),
        difficulty_changed_map_ids=difficulty_changed_map_ids,
    )

    await session.commit()
    session.expire_all()

    return MapSyncResult(
        processed=len(maps_data),
        created=created,
        updated=updated,
        errors=errors,
    )
