from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models import GlobalApiSyncResult, RecordFilter, legacy_mode_id_to_kz_mode

RECORD_FILTER_DATETIME_FALLBACK = "2018-07-10T21:02:51"
_RECORD_FILTER_DATETIME_FALLBACK_VALUE = datetime.fromisoformat(
    RECORD_FILTER_DATETIME_FALLBACK
).replace(tzinfo=UTC)


class GlobalApiRecordFilterSyncError(RuntimeError):
    pass


def _normalize_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.year < 1900:
            return _RECORD_FILTER_DATETIME_FALLBACK_VALUE
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return _RECORD_FILTER_DATETIME_FALLBACK_VALUE
        if parsed.year < 1900:
            return _RECORD_FILTER_DATETIME_FALLBACK_VALUE
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)

    return _RECORD_FILTER_DATETIME_FALLBACK_VALUE


def _parse_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
    return default


def _parse_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    parsed = str(value).strip()
    return parsed or None


def _record_filter_values_from_globalapi(payload: dict[str, Any]) -> dict[str, Any] | None:
    record_filter_id = _parse_int(payload.get("id"), default=-1)
    map_id = _parse_int(payload.get("map_id"), default=-2)
    mode_id = _parse_int(payload.get("mode_id"), default=-1)
    tickrate = _parse_int(payload.get("tickrate"), default=0)

    if record_filter_id < 0 or mode_id < 0 or tickrate <= 0 or map_id < -1:
        return None

    return {
        "id": record_filter_id,
        "map_id": map_id,
        "stage": _parse_int(payload.get("stage", 0), default=0),
        "mode": legacy_mode_id_to_kz_mode(mode_id),
        "tickrate": tickrate,
        "has_teleports": _parse_bool(payload.get("has_teleports"), default=False),
        "created_at": _normalize_datetime(payload.get("created_on")),
        "updated_at": _normalize_datetime(payload.get("updated_on")),
        "updated_by_id": _parse_optional_string(payload.get("updated_by_id")),
    }


async def fetch_record_filters_from_globalapi(
    *,
    client: httpx.AsyncClient | None = None,
    offset: int,
    limit: int,
) -> list[dict[str, Any]]:
    close_client = client is None
    resolved_client = client or httpx.AsyncClient(timeout=settings.GLOBALAPI_TIMEOUT_SECONDS)
    try:
        response = await resolved_client.get(
            f"{settings.GLOBALAPI_BASE_URL}/record_filters",
            params={"offset": offset, "limit": limit},
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise GlobalApiRecordFilterSyncError(
            "Failed to fetch record filters from GlobalAPI"
        ) from exc
    finally:
        if close_client:
            await resolved_client.aclose()

    try:
        payload = response.json()
    except ValueError as exc:
        raise GlobalApiRecordFilterSyncError(
            "GlobalAPI returned invalid record filter payload"
        ) from exc

    if not isinstance(payload, list):
        raise GlobalApiRecordFilterSyncError(
            "GlobalAPI returned unexpected record filter payload type"
        )

    return [item for item in payload if isinstance(item, dict)]


async def sync_record_filters_from_globalapi(
    *,
    session: AsyncSession,
) -> GlobalApiSyncResult:
    processed = 0
    created = 0
    updated = 0
    errors = 0
    duplicate_ids: set[int] = set()
    seen_ids: set[int] = set()

    # GlobalAPI record filters are treated as append/update-only metadata for now.
    # If upstream ever starts deleting filters, revisit this assumption and add a
    # stale-row policy instead of silently removing local rows.
    async with httpx.AsyncClient(timeout=settings.GLOBALAPI_TIMEOUT_SECONDS) as client:
        offset = 0
        while True:
            payloads = await fetch_record_filters_from_globalapi(
                client=client,
                offset=offset,
                limit=settings.GLOBALAPI_RECORD_FILTERS_LIMIT,
            )

            if not payloads:
                break

            rows_by_id: dict[int, dict[str, Any]] = {}
            page_processed = 0
            for payload in payloads:
                record_filter_id = _parse_int(payload.get("id"), default=-1)
                if record_filter_id < 0:
                    errors += 1
                    continue

                if record_filter_id in seen_ids:
                    duplicate_ids.add(record_filter_id)
                    continue

                row = _record_filter_values_from_globalapi(payload)
                if row is None:
                    errors += 1
                    seen_ids.add(record_filter_id)
                    continue

                seen_ids.add(record_filter_id)
                rows_by_id[record_filter_id] = row
                page_processed += 1

            if rows_by_id:
                record_filter_ids = list(rows_by_id.keys())
                existing_ids = set(
                    (
                        await session.exec(
                            select(RecordFilter.id).where(
                                RecordFilter.id.in_(record_filter_ids)
                            )
                        )
                    ).all()
                )
                created += sum(
                    1 for record_filter_id in record_filter_ids if record_filter_id not in existing_ids
                )
                updated += sum(
                    1 for record_filter_id in record_filter_ids if record_filter_id in existing_ids
                )

                table = RecordFilter.__table__
                insert_statement = pg_insert(table).values(list(rows_by_id.values()))
                upsert_statement = insert_statement.on_conflict_do_update(
                    index_elements=[table.c.id],
                    set_={
                        "map_id": insert_statement.excluded.map_id,
                        "stage": insert_statement.excluded.stage,
                        "mode": insert_statement.excluded.mode,
                        "tickrate": insert_statement.excluded.tickrate,
                        "has_teleports": insert_statement.excluded.has_teleports,
                        "created_at": insert_statement.excluded.created_at,
                        "updated_at": insert_statement.excluded.updated_at,
                        "updated_by_id": insert_statement.excluded.updated_by_id,
                    },
                )
                await session.exec(upsert_statement)
                await session.commit()
                session.expire_all()

            processed += page_processed
            if len(payloads) < settings.GLOBALAPI_RECORD_FILTERS_LIMIT:
                break
            offset += settings.GLOBALAPI_RECORD_FILTERS_LIMIT

    return GlobalApiSyncResult(
        processed=processed,
        created=created,
        updated=updated,
        errors=errors,
        warnings=len(duplicate_ids),
    )
