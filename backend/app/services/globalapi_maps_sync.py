import re
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Map, MapSyncResult

GLOBALAPI_MAPS_URL = "https://kztimerglobal.com/api/v2.0/maps"
GLOBALAPI_MAPS_LIMIT = 9999
GLOBALAPI_TIMEOUT_SECONDS = 45.0
MAP_DATETIME_FALLBACK = "2018-01-09T10:45:50"
_MAP_DATETIME_FALLBACK_VALUE = datetime.fromisoformat(MAP_DATETIME_FALLBACK).replace(
    tzinfo=UTC
)
_WORKSHOP_ID_PATTERN = re.compile(r"[?&]id=(\d+)")


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


def _parse_string_list(value: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        return [stripped]
    return None


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
        "authors": _parse_string_list(payload.get("authors")),
        "no_steamid_names": _parse_string_list(payload.get("no_steamid_names")),
    }


async def fetch_maps_from_globalapi() -> list[dict[str, Any]]:
    try:
        async with httpx.AsyncClient(timeout=GLOBALAPI_TIMEOUT_SECONDS) as client:
            response = await client.get(
                GLOBALAPI_MAPS_URL,
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
    existing_ids_statement = select(Map.id).where(Map.id.in_(map_ids))
    existing_ids = set((await session.exec(existing_ids_statement)).all())
    created = sum(1 for map_id in map_ids if map_id not in existing_ids)
    updated = len(map_ids) - created

    map_table = Map.__table__
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

    await session.commit()
    session.expire_all()

    return MapSyncResult(
        processed=len(maps_data),
        created=created,
        updated=updated,
        errors=errors,
    )
