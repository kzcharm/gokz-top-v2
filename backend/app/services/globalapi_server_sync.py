import logging
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models import GlobalApiSyncResult, ServerGlobalapi

DEFAULT_SERVER_PORT = 27015
SERVER_DATETIME_FALLBACK = "2018-01-09T10:45:50"
_SERVER_DATETIME_FALLBACK_VALUE = datetime.fromisoformat(
    SERVER_DATETIME_FALLBACK
).replace(tzinfo=UTC)

logger = logging.getLogger(__name__)


class GlobalApiServerSyncError(RuntimeError):
    pass


def _normalize_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.year < 1900:
            return _SERVER_DATETIME_FALLBACK_VALUE
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return _SERVER_DATETIME_FALLBACK_VALUE
        if parsed.year < 1900:
            return _SERVER_DATETIME_FALLBACK_VALUE
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)

    return _SERVER_DATETIME_FALLBACK_VALUE


def _parse_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    parsed = str(value).strip()
    return parsed or None


def _normalize_port(value: Any) -> int:
    parsed = _parse_int(value, default=DEFAULT_SERVER_PORT)
    if 1 <= parsed <= 65535:
        return parsed
    return DEFAULT_SERVER_PORT


def _server_values_from_globalapi(
    *,
    payload: dict[str, Any],
    approval_status: int,
    synced_at: datetime,
) -> dict[str, Any]:
    return {
        "port": _normalize_port(payload.get("port")),
        "ip": _parse_optional_string(payload.get("ip")),
        "name": _parse_optional_string(payload.get("name")),
        "owner_steamid64": _parse_int(payload.get("owner_steamid64"), default=0),
        "approval_status": approval_status,
        "approved_by_steamid64": _parse_int(
            payload.get("approved_by_steamid64"), default=0
        ),
        "created_on": _normalize_datetime(payload.get("created_on")),
        "updated_on": _normalize_datetime(payload.get("updated_on")),
        "synced_at": synced_at,
    }


async def fetch_servers_from_globalapi(
    *,
    approval_status: int,
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    close_client = client is None
    resolved_client = client or httpx.AsyncClient(timeout=settings.GLOBALAPI_TIMEOUT_SECONDS)
    try:
        response = await resolved_client.get(
            f"{settings.GLOBALAPI_BASE_URL}/servers",
            params={
                "approval_status": approval_status,
                "limit": settings.GLOBALAPI_SERVERS_LIMIT,
            },
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise GlobalApiServerSyncError(
            f"Failed to fetch servers from GlobalAPI for approval_status={approval_status}"
        ) from exc
    finally:
        if close_client:
            await resolved_client.aclose()

    try:
        payload = response.json()
    except ValueError as exc:
        raise GlobalApiServerSyncError(
            f"GlobalAPI returned invalid server payload for approval_status={approval_status}"
        ) from exc

    if not isinstance(payload, list):
        raise GlobalApiServerSyncError(
            f"GlobalAPI returned unexpected server payload type for approval_status={approval_status}"
        )

    return [item for item in payload if isinstance(item, dict)]


async def sync_servers_from_globalapi(*, session: AsyncSession) -> GlobalApiSyncResult:
    async with httpx.AsyncClient(timeout=settings.GLOBALAPI_TIMEOUT_SECONDS) as client:
        unapproved_servers = await fetch_servers_from_globalapi(
            approval_status=0,
            client=client,
        )
        approved_servers = await fetch_servers_from_globalapi(
            approval_status=1,
            client=client,
        )

    now = datetime.now(UTC)
    processed = len(unapproved_servers) + len(approved_servers)
    rows_by_id: dict[int, dict[str, Any]] = {}
    duplicate_ids: set[int] = set()
    errors = 0

    for approval_status, payloads in ((0, unapproved_servers), (1, approved_servers)):
        for payload in payloads:
            server_id = _parse_int(payload.get("id"), default=-1)
            if server_id < 0:
                errors += 1
                continue

            row = {
                "id": server_id,
                **_server_values_from_globalapi(
                    payload=payload,
                    approval_status=approval_status,
                    synced_at=now,
                ),
            }
            existing_row = rows_by_id.get(server_id)
            if existing_row is not None:
                duplicate_ids.add(server_id)
                if approval_status >= int(existing_row["approval_status"]):
                    rows_by_id[server_id] = row
                continue

            rows_by_id[server_id] = row

    if duplicate_ids:
        logger.warning(
            "GlobalAPI server sync found duplicate ids across approval sets: %s",
            sorted(duplicate_ids),
        )

    if not rows_by_id:
        return GlobalApiSyncResult(
            processed=processed,
            created=0,
            updated=0,
            errors=errors,
            warnings=len(duplicate_ids),
        )

    server_ids = list(rows_by_id.keys())
    existing_servers = {
        server.id: server
        for server in (
            await session.exec(
                select(ServerGlobalapi).where(ServerGlobalapi.id.in_(server_ids))
            )
        ).all()
    }
    created = sum(1 for server_id in server_ids if server_id not in existing_servers)

    server_table = ServerGlobalapi.__table__
    rows_to_insert = [
        row for server_id, row in rows_by_id.items() if server_id not in existing_servers
    ]
    rows_to_update = [
        (server_id, int(row["approval_status"]))
        for server_id, row in rows_by_id.items()
        if (existing_server := existing_servers.get(server_id)) is not None
        and existing_server.approval_status != int(row["approval_status"])
    ]
    updated = len(rows_to_update)

    if rows_to_insert:
        insert_statement = pg_insert(server_table).values(rows_to_insert)
        await session.exec(insert_statement.on_conflict_do_nothing(index_elements=[server_table.c.id]))

    for server_id, approval_status in rows_to_update:
        await session.exec(
            update(ServerGlobalapi)
            .where(ServerGlobalapi.id == server_id)
            .values(approval_status=approval_status)
        )
    await session.commit()
    session.expire_all()

    return GlobalApiSyncResult(
        processed=processed,
        created=created,
        updated=updated,
        errors=errors,
        warnings=len(duplicate_ids),
    )
