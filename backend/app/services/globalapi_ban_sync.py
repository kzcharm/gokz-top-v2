from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models import Ban, BanType, GlobalApiSyncResult, GlobalApiSyncState

logger = logging.getLogger(__name__)

_BAN_DATETIME_FALLBACK = datetime(2018, 1, 9, 10, 45, 50, tzinfo=UTC)
_PERMANENT_BAN_SENTINEL = datetime(9999, 12, 31, 23, 59, 59, tzinfo=UTC)


class GlobalApiBanSyncError(RuntimeError):
    pass


def _normalize_datetime(value: Any) -> datetime | None:
    if value in {None, ""}:
        return None

    if isinstance(value, datetime):
        if value.year < 1900:
            return _BAN_DATETIME_FALLBACK
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return _BAN_DATETIME_FALLBACK
        if parsed.year < 1900:
            return _BAN_DATETIME_FALLBACK
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)

    return _BAN_DATETIME_FALLBACK


def _normalize_ban_expiry(value: Any) -> datetime | None:
    expires_on = _normalize_datetime(value)
    if expires_on is None:
        return None
    if expires_on >= _PERMANENT_BAN_SENTINEL:
        return None
    return expires_on


def _parse_int(value: Any, *, default: int | None = None) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    parsed = str(value).strip()
    return parsed or None


def _parse_ban_type(value: Any) -> BanType | None:
    if not isinstance(value, str):
        return None
    try:
        return BanType(value.strip())
    except ValueError:
        return None


def _ban_values_from_globalapi(
    *,
    payload: dict[str, Any],
    synced_at: datetime,
) -> dict[str, Any] | None:
    ban_id = _parse_int(payload.get("id"), default=None)
    steamid64 = _parse_int(payload.get("steamid64"), default=None)
    ban_type = _parse_ban_type(payload.get("ban_type"))
    if ban_id is None or steamid64 is None or ban_type is None:
        return None

    return {
        "id": ban_id,
        "ban_type": ban_type,
        "expires_on": _normalize_ban_expiry(payload.get("expires_on")),
        "ip": _parse_optional_string(payload.get("ip")),
        "steamid64": steamid64,
        "player_name": _parse_optional_string(payload.get("player_name")),
        "notes": _parse_optional_string(payload.get("notes")),
        "stats": _parse_optional_string(payload.get("stats")),
        "server_id": _parse_int(payload.get("server_id"), default=None),
        "updated_by_id": _parse_optional_string(payload.get("updated_by_id")),
        "created_on": _normalize_datetime(payload.get("created_on"))
        or _BAN_DATETIME_FALLBACK,
        "updated_on": _normalize_datetime(payload.get("updated_on"))
        or _BAN_DATETIME_FALLBACK,
        "synced_at": synced_at,
    }


async def fetch_bans_from_globalapi(
    *,
    client: httpx.AsyncClient | None = None,
    offset: int,
    limit: int,
    updated_since: datetime | None = None,
) -> list[dict[str, Any]]:
    close_client = client is None
    resolved_client = client or httpx.AsyncClient(timeout=settings.GLOBALAPI_TIMEOUT_SECONDS)
    params: dict[str, Any] = {"offset": offset, "limit": limit}
    if updated_since is not None:
        params["updated_since"] = updated_since.isoformat()

    try:
        response = await resolved_client.get(
            f"{settings.GLOBALAPI_BASE_URL}/bans",
            params=params,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise GlobalApiBanSyncError("Failed to fetch bans from GlobalAPI") from exc
    finally:
        if close_client:
            await resolved_client.aclose()

    try:
        payload = response.json()
    except ValueError as exc:
        raise GlobalApiBanSyncError("GlobalAPI returned invalid ban payload") from exc

    if not isinstance(payload, list):
        raise GlobalApiBanSyncError("GlobalAPI returned unexpected ban payload type")

    return [item for item in payload if isinstance(item, dict)]


async def sync_bans_from_globalapi(
    *,
    session: AsyncSession,
) -> GlobalApiSyncResult:
    sync_state = await session.get(GlobalApiSyncState, "bans")
    updated_since: datetime | None = None
    limit = settings.GLOBALAPI_BANS_BACKFILL_LIMIT
    if sync_state is not None and sync_state.last_successful_at is not None:
        updated_since = sync_state.last_successful_at - timedelta(
            seconds=settings.GLOBALAPI_BANS_INCREMENTAL_OVERLAP_SECONDS
        )
        limit = settings.GLOBALAPI_BANS_INCREMENTAL_LIMIT

    processed = 0
    created = 0
    updated = 0
    errors = 0
    warnings = 0
    offset = 0
    seen_ids: set[int] = set()

    # GlobalAPI bans are treated as append/update-only for sync purposes.
    # If upstream ever starts deleting or removing bans, revisit this policy
    # instead of silently deleting local rows here.
    async with httpx.AsyncClient(timeout=settings.GLOBALAPI_TIMEOUT_SECONDS) as client:
        while True:
            payloads = await fetch_bans_from_globalapi(
                client=client,
                offset=offset,
                limit=limit,
                updated_since=updated_since,
            )
            if not payloads:
                break

            rows_by_id: dict[int, dict[str, Any]] = {}
            for payload in payloads:
                ban_id = _parse_int(payload.get("id"), default=None)
                if ban_id is None:
                    errors += 1
                    continue
                if ban_id in seen_ids:
                    warnings += 1
                    continue

                row = _ban_values_from_globalapi(payload=payload, synced_at=datetime.now(UTC))
                if row is None:
                    errors += 1
                    seen_ids.add(ban_id)
                    continue

                seen_ids.add(ban_id)
                rows_by_id[ban_id] = row

            if rows_by_id:
                ban_ids = list(rows_by_id.keys())
                existing_ids = set(
                    (
                        await session.exec(select(Ban.id).where(Ban.id.in_(ban_ids)))
                    ).all()
                )
                created += sum(1 for ban_id in ban_ids if ban_id not in existing_ids)
                updated += sum(1 for ban_id in ban_ids if ban_id in existing_ids)

                table = Ban.__table__
                insert_statement = pg_insert(table).values(list(rows_by_id.values()))
                upsert_statement = insert_statement.on_conflict_do_update(
                    index_elements=[table.c.id],
                    set_={
                        "ban_type": insert_statement.excluded.ban_type,
                        "expires_on": insert_statement.excluded.expires_on,
                        "ip": insert_statement.excluded.ip,
                        "steamid64": insert_statement.excluded.steamid64,
                        "player_name": insert_statement.excluded.player_name,
                        "notes": insert_statement.excluded.notes,
                        "stats": insert_statement.excluded.stats,
                        "server_id": insert_statement.excluded.server_id,
                        "updated_by_id": insert_statement.excluded.updated_by_id,
                        "created_on": insert_statement.excluded.created_on,
                        "updated_on": insert_statement.excluded.updated_on,
                        "synced_at": insert_statement.excluded.synced_at,
                    },
                )
                await session.exec(upsert_statement)
                await session.commit()
                session.expire_all()

            processed += len(rows_by_id)
            if len(payloads) < limit:
                break
            offset += limit

    return GlobalApiSyncResult(
        processed=processed,
        created=created,
        updated=updated,
        errors=errors,
        warnings=warnings,
    )
