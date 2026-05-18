from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import String, case, cast, func, or_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.core.config import settings
from app.models import Ban, BanType, GlobalApiSyncResult, GlobalApiSyncState, Player

logger = logging.getLogger(__name__)

_BAN_DATETIME_FALLBACK = datetime(2018, 1, 9, 10, 45, 50, tzinfo=UTC)
_PERMANENT_BAN_SENTINEL = datetime(9999, 12, 31, 23, 59, 59, tzinfo=UTC)


class GlobalApiBanSyncError(RuntimeError):
    pass


@dataclass(frozen=True)
class PlayerBanSyncResult:
    cleared_active_ban_count: int
    remaining_active_ban_count: int


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
        "notes": _parse_optional_string(payload.get("notes")),
        "stats": _parse_optional_string(payload.get("stats")),
        "server_id": _parse_int(payload.get("server_id"), default=None),
        "updated_by_id": _parse_optional_string(payload.get("updated_by_id")),
        "created_at": _normalize_datetime(payload.get("created_on"))
        or _BAN_DATETIME_FALLBACK,
        "updated_at": _normalize_datetime(payload.get("updated_on"))
        or _BAN_DATETIME_FALLBACK,
        "synced_at": synced_at,
    }


def _player_values_from_globalapi_ban(
    *,
    payload: dict[str, Any],
    synced_at: datetime,
) -> dict[str, Any] | None:
    steamid64 = _parse_int(payload.get("steamid64"), default=None)
    if steamid64 is None:
        return None

    ban_created_at = _normalize_datetime(payload.get("created_on")) or synced_at
    player_name = _parse_optional_string(payload.get("player_name")) or str(steamid64)
    return {
        "steamid64": steamid64,
        "name": player_name,
        "created_at": ban_created_at,
        "updated_at": synced_at,
    }


async def _upsert_players_for_bans(
    *,
    session: AsyncSession,
    payloads: list[dict[str, Any]],
    synced_at: datetime,
) -> None:
    player_table = Player.__table__  # type: ignore[attr-defined]
    players_by_steamid64: dict[int, dict[str, Any]] = {}
    for payload in payloads:
        row = _player_values_from_globalapi_ban(payload=payload, synced_at=synced_at)
        if row is None:
            continue

        steamid64 = int(row["steamid64"])
        existing = players_by_steamid64.get(steamid64)
        if existing is None:
            players_by_steamid64[steamid64] = row
            continue

        if row["created_at"] < existing["created_at"]:
            existing["created_at"] = row["created_at"]
        if row["name"] != str(steamid64):
            existing["name"] = row["name"]

    if not players_by_steamid64:
        return

    insert_statement = pg_insert(player_table).values(list(players_by_steamid64.values()))
    await session.exec(
        insert_statement.on_conflict_do_update(
            index_elements=[player_table.c.steamid64],
            set_={
                "name": case(
                    (
                        or_(
                            player_table.c.name.is_(None),
                            player_table.c.name == "",
                            player_table.c.name == cast(
                                player_table.c.steamid64, String
                            ),
                        ),
                        insert_statement.excluded.name,
                    ),
                    else_=player_table.c.name,
                ),
                "created_at": case(
                    (
                        player_table.c.created_at.is_(None),
                        insert_statement.excluded.created_at,
                    ),
                    (
                        player_table.c.created_at > insert_statement.excluded.created_at,
                        insert_statement.excluded.created_at,
                    ),
                    else_=player_table.c.created_at,
                ),
                "updated_at": case(
                    (
                        or_(
                            player_table.c.updated_at.is_(None),
                            player_table.c.name.is_(None),
                            player_table.c.name == "",
                            player_table.c.name == cast(
                                player_table.c.steamid64, String
                            ),
                        ),
                        insert_statement.excluded.updated_at,
                    ),
                    else_=player_table.c.updated_at,
                ),
            },
        )
    )


async def fetch_bans_from_globalapi(
    *,
    client: httpx.AsyncClient | None = None,
    offset: int,
    limit: int,
    steamid64: int | None = None,
    created_since: datetime | None = None,
    updated_since: datetime | None = None,
) -> list[dict[str, Any]]:
    close_client = client is None
    resolved_client = client or httpx.AsyncClient(timeout=settings.GLOBALAPI_TIMEOUT_SECONDS)
    params: dict[str, Any] = {"offset": offset, "limit": limit}
    if steamid64 is not None:
        params["steamid64"] = steamid64
    if created_since is not None:
        params["created_since"] = created_since.isoformat()
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


async def _upsert_ban_payloads(
    *,
    session: AsyncSession,
    payloads: list[dict[str, Any]],
    synced_at: datetime,
    seen_ids: set[int] | None = None,
) -> tuple[int, int, int, int, int, set[int]]:
    rows_by_id: dict[int, dict[str, Any]] = {}
    player_payloads: list[dict[str, Any]] = []
    errors = 0
    warnings = 0
    resolved_seen_ids = seen_ids if seen_ids is not None else set()

    for payload in payloads:
        ban_id = _parse_int(payload.get("id"), default=None)
        if ban_id is None:
            errors += 1
            continue
        if ban_id in resolved_seen_ids:
            warnings += 1
            continue

        row = _ban_values_from_globalapi(payload=payload, synced_at=synced_at)
        if row is None:
            errors += 1
            resolved_seen_ids.add(ban_id)
            continue

        resolved_seen_ids.add(ban_id)
        rows_by_id[ban_id] = row
        player_payloads.append(payload)

    if not rows_by_id:
        return 0, 0, 0, errors, warnings, set()

    ban_ids = list(rows_by_id.keys())
    table = Ban.__table__  # type: ignore[attr-defined]
    touched_steamid64s = {int(row["steamid64"]) for row in rows_by_id.values()}
    existing_ids = set(
        (await session.exec(select(table.c.id).where(table.c.id.in_(ban_ids)))).all()
    )
    created = sum(1 for ban_id in ban_ids if ban_id not in existing_ids)
    updated = sum(1 for ban_id in ban_ids if ban_id in existing_ids)

    await _upsert_players_for_bans(
        session=session,
        payloads=player_payloads,
        synced_at=synced_at,
    )

    insert_statement = pg_insert(table).values(list(rows_by_id.values()))
    upsert_statement = insert_statement.on_conflict_do_update(
        index_elements=[table.c.id],
        index_where=table.c.id.is_not(None),
        set_={
            "ban_type": insert_statement.excluded.ban_type,
            "expires_on": insert_statement.excluded.expires_on,
            "ip": insert_statement.excluded.ip,
            "steamid64": insert_statement.excluded.steamid64,
            "notes": insert_statement.excluded.notes,
            "stats": insert_statement.excluded.stats,
            "server_id": insert_statement.excluded.server_id,
            "updated_by_id": insert_statement.excluded.updated_by_id,
            "created_at": insert_statement.excluded.created_at,
            "updated_at": insert_statement.excluded.updated_at,
            "synced_at": insert_statement.excluded.synced_at,
        },
    )
    await session.exec(upsert_statement)

    return len(rows_by_id), created, updated, errors, warnings, touched_steamid64s


async def _load_active_ban_ids_for_player(
    *,
    session: AsyncSession,
    steamid64: int,
    now: datetime | None = None,
    external_only: bool = False,
) -> set[str]:
    current_time = now or datetime.now(UTC)
    statement = select(Ban.id).where(
        Ban.steamid64 == steamid64,
        or_(
            Ban.expires_on.is_(None),
            Ban.expires_on >= current_time,
        ),
    )
    if external_only:
        statement = statement.where(Ban.id.is_not(None))
        return {str(ban_id) for ban_id in (await session.exec(statement)).all()}

    return {
        str(ban_uuid)
        for ban_uuid in (
            await session.exec(
                select(Ban.uuid).where(
                    Ban.steamid64 == steamid64,
                    or_(
                        Ban.expires_on.is_(None),
                        Ban.expires_on >= current_time,
                    ),
                )
            )
        ).all()
    }


async def sync_bans_from_globalapi(
    *,
    session: AsyncSession,
) -> GlobalApiSyncResult:
    sync_state = await session.get(GlobalApiSyncState, "bans")
    created_since: datetime | None = None
    limit = settings.GLOBALAPI_BANS_BACKFILL_LIMIT
    latest_local_created_at = await session.exec(
        select(func.max(Ban.created_at)).where(Ban.id.is_not(None))
    )
    incremental_anchor = latest_local_created_at.one()
    if (
        sync_state is not None
        and sync_state.last_successful_at is not None
        and incremental_anchor is not None
    ):
        # GlobalAPI's bans endpoint currently honors created_since for new rows but
        # does not reliably return rows for updated_since filters.
        created_since = min(
            sync_state.last_successful_at,
            incremental_anchor,
        ) - timedelta(
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
    touched_steamid64s: set[int] = set()

    # GlobalAPI bans are treated as append/update-only for sync purposes.
    # If upstream ever starts deleting or removing bans, revisit this policy
    # instead of silently deleting local rows here.
    async with httpx.AsyncClient(timeout=settings.GLOBALAPI_TIMEOUT_SECONDS) as client:
        while True:
            synced_at = datetime.now(UTC)
            payloads = await fetch_bans_from_globalapi(
                client=client,
                offset=offset,
                limit=limit,
                created_since=created_since,
            )
            if not payloads:
                break

            (
                processed_page,
                created_page,
                updated_page,
                errors_page,
                warnings_page,
                touched_page,
            ) = await _upsert_ban_payloads(
                session=session,
                payloads=payloads,
                synced_at=synced_at,
                seen_ids=seen_ids,
            )
            processed += processed_page
            created += created_page
            updated += updated_page
            errors += errors_page
            warnings += warnings_page
            touched_steamid64s.update(touched_page)

            if processed_page > 0:
                await session.commit()
                session.expire_all()

            if len(payloads) < limit:
                break
            offset += limit

    if touched_steamid64s:
        await crud.rebuild_leaderboard_players(
            session=session,
            steamid64s=sorted(touched_steamid64s),
        )
        await session.commit()
        session.expire_all()

    return GlobalApiSyncResult(
        processed=processed,
        created=created,
        updated=updated,
        errors=errors,
        warnings=warnings,
    )


async def sync_player_bans_from_globalapi(
    *,
    session: AsyncSession,
    steamid64: int,
) -> PlayerBanSyncResult:
    before_active_ban_ids = await _load_active_ban_ids_for_player(
        session=session,
        steamid64=steamid64,
        external_only=True,
    )
    offset = 0
    limit = settings.GLOBALAPI_BANS_BACKFILL_LIMIT
    seen_ids: set[int] = set()

    async with httpx.AsyncClient(timeout=settings.GLOBALAPI_TIMEOUT_SECONDS) as client:
        while True:
            synced_at = datetime.now(UTC)
            payloads = await fetch_bans_from_globalapi(
                client=client,
                offset=offset,
                limit=limit,
                steamid64=steamid64,
            )
            if not payloads:
                break

            (
                processed_page,
                _created_page,
                _updated_page,
                _errors_page,
                _warnings_page,
                _touched_page,
            ) = await _upsert_ban_payloads(
                session=session,
                payloads=payloads,
                synced_at=synced_at,
                seen_ids=seen_ids,
            )
            if processed_page > 0:
                await session.commit()
                session.expire_all()

            if len(payloads) < limit:
                break
            offset += limit

    after_active_ban_ids = await _load_active_ban_ids_for_player(
        session=session,
        steamid64=steamid64,
        external_only=True,
    )
    if before_active_ban_ids != after_active_ban_ids:
        await crud.rebuild_leaderboard_players(
            session=session,
            steamid64s=[steamid64],
        )
        await session.commit()
        session.expire_all()

    return PlayerBanSyncResult(
        cleared_active_ban_count=len(before_active_ban_ids - after_active_ban_ids),
        remaining_active_ban_count=len(after_active_ban_ids),
    )
