import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

import httpx
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.core.config import settings
from app.models import (
    GlobalApiSyncResult,
    GlobalApiSyncState,
    Map,
    Player,
    ServerGlobalapi,
    get_datetime_utc,
)

DEFAULT_RECORD_START_ID = 200
NULL_PROBE_WINDOW = 4
RATE_LIMIT_SLEEP_SECONDS = 300
NULL_SLEEP_SECONDS = 1

logger = logging.getLogger(__name__)


class GlobalApiRecordSyncError(RuntimeError):
    pass


class GlobalApiRecordSyncRateLimitError(GlobalApiRecordSyncError):
    pass


@dataclass(frozen=True, slots=True)
class RecordFetchResult:
    kind: Literal["record", "null"]
    payload: dict[str, Any] | None = None


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
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"Invalid {field_name}") from exc


def _parse_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid optional integer field") from exc


async def _get_or_create_records_sync_state(
    *,
    session: AsyncSession,
) -> GlobalApiSyncState:
    state = await session.get(GlobalApiSyncState, "records")
    if state is not None:
        return state

    state = GlobalApiSyncState(task_name="records")
    session.add(state)
    await session.commit()
    await session.refresh(state)
    return state


async def _fetch_record_once(
    *,
    client: httpx.AsyncClient,
    record_id: int,
) -> RecordFetchResult:
    try:
        response = await client.get(f"{settings.GLOBALAPI_BASE_URL}/records/{record_id}")
    except httpx.HTTPError as exc:
        raise GlobalApiRecordSyncError(
            f"Failed to fetch record {record_id} from GlobalAPI"
        ) from exc

    if response.status_code == 429:
        raise GlobalApiRecordSyncRateLimitError(f"Rate limited for record {record_id}")
    if response.status_code == 404:
        return RecordFetchResult(kind="null")
    if response.status_code >= 400:
        raise GlobalApiRecordSyncError(
            f"GlobalAPI returned {response.status_code} for record {record_id}"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise GlobalApiRecordSyncError(
            f"GlobalAPI returned invalid JSON for record {record_id}"
        ) from exc

    if payload is None:
        return RecordFetchResult(kind="null")
    if not isinstance(payload, dict):
        raise GlobalApiRecordSyncError(
            f"GlobalAPI returned unexpected payload for record {record_id}"
        )
    return RecordFetchResult(kind="record", payload=payload)


async def _fetch_record_with_retry(
    *,
    client: httpx.AsyncClient,
    record_id: int,
) -> RecordFetchResult:
    while True:
        try:
            return await _fetch_record_once(client=client, record_id=record_id)
        except GlobalApiRecordSyncRateLimitError:
            logger.warning(
                "GlobalAPI record sync hit rate limit for record_id=%s; retrying in %ss",
                record_id,
                RATE_LIMIT_SLEEP_SECONDS,
            )
            await asyncio.sleep(RATE_LIMIT_SLEEP_SECONDS)


async def _hydrate_main_stage_points_from_top(
    *,
    client: httpx.AsyncClient,
    payload: dict[str, Any],
) -> dict[str, Any]:
    record_id = payload.get("id")
    try:
        parsed_record_id = _parse_int(record_id, field_name="id")
        stage = _parse_int(payload.get("stage", 0), field_name="stage")
        if stage != 0:
            return payload

        steamid64 = _parse_int(payload.get("steamid64"), field_name="steamid64")
        map_id = _parse_int(payload.get("map_id"), field_name="map_id")
        mode_name = _parse_string(payload.get("mode"))
        if not mode_name:
            return payload
        teleports = _parse_int(payload.get("teleports", 0), field_name="teleports")
    except ValueError as exc:
        logger.warning(
            "Skipping GlobalAPI top points lookup for malformed record record_id=%s: %s",
            record_id,
            exc,
        )
        return payload

    try:
        response = await client.get(
            f"{settings.GLOBALAPI_BASE_URL}/records/top",
            params={
                "steamid64": steamid64,
                "map_id": map_id,
                "stage": 0,
                "modes_list_string": mode_name,
                "has_teleports": teleports > 0,
                "tickrate": 128,
                "limit": 1,
            },
        )
    except httpx.HTTPError as exc:
        logger.warning(
            "Failed to hydrate GlobalAPI points from records/top for record_id=%s: %s",
            parsed_record_id,
            exc,
        )
        return payload

    if response.status_code >= 400:
        logger.warning(
            "GlobalAPI records/top returned %s while hydrating points for record_id=%s",
            response.status_code,
            parsed_record_id,
        )
        return payload

    try:
        top_payload = response.json()
    except ValueError:
        logger.warning(
            "GlobalAPI records/top returned invalid JSON while hydrating points for record_id=%s",
            parsed_record_id,
        )
        return payload

    if not isinstance(top_payload, list) or not top_payload:
        return payload

    top_record = top_payload[0]
    if not isinstance(top_record, dict):
        logger.warning(
            "GlobalAPI records/top returned unexpected payload item while hydrating points for record_id=%s",
            parsed_record_id,
        )
        return payload

    try:
        top_record_id = _parse_int(top_record.get("id"), field_name="id")
        points = _parse_int(top_record.get("points", 0), field_name="points")
    except ValueError as exc:
        logger.warning(
            "Skipping malformed GlobalAPI records/top payload for record_id=%s: %s",
            parsed_record_id,
            exc,
        )
        return payload

    if top_record_id != parsed_record_id:
        return payload
    if not 0 <= points <= 1000:
        logger.warning(
            "Skipping out-of-range GlobalAPI records/top points for record_id=%s: %s",
            parsed_record_id,
            points,
        )
        return payload

    hydrated_payload = dict(payload)
    hydrated_payload["points"] = points
    return hydrated_payload


async def _ensure_player(
    *,
    session: AsyncSession,
    steamid64: int,
    player_name: str,
    created_on: datetime,
) -> Player:
    player = await crud.get_player_by_steamid64(session=session, steamid64=steamid64)
    steam_data = await crud._fetch_player_from_steam_api(steamid64)
    steam_name = _parse_string(steam_data.get("name"))
    resolved_name = (
        steam_name
        if steam_name and steam_name != str(steamid64)
        else player_name or str(steamid64)
    )

    if player is None:
        player = Player(
            steamid64=steamid64,
            name=resolved_name,
            custom_id=crud.normalize_custom_id(steam_data.get("custom_id")),
            avatar_hash=steam_data.get("avatar_hash"),
            country=steam_data.get("country"),
            created_at=created_on,
            last_played_at=created_on,
            updated_at=get_datetime_utc(),
        )
        session.add(player)
        return player

    if resolved_name and player.name == str(steamid64):
        player.name = resolved_name
    elif steam_name and steam_name != str(steamid64):
        player.name = steam_name
    if steam_data.get("custom_id"):
        normalized_custom_id = crud.normalize_custom_id(steam_data["custom_id"])
        if normalized_custom_id:
            player.custom_id = normalized_custom_id
    if steam_data.get("avatar_hash"):
        player.avatar_hash = steam_data["avatar_hash"]
    if steam_data.get("country") and not player.is_country_locked:
        player.country = steam_data["country"]
    if player.created_at is None or created_on < player.created_at:
        player.created_at = created_on
    if player.last_played_at is None or created_on > player.last_played_at:
        player.last_played_at = created_on
    player.updated_at = get_datetime_utc()
    session.add(player)
    return player


async def _ensure_map(
    *,
    session: AsyncSession,
    map_id: int,
    map_name: str,
) -> Map:
    map_obj = await crud.get_map_by_id(session=session, id=map_id)
    if map_obj is not None:
        return map_obj

    now = get_datetime_utc()
    map_obj = Map(
        id=map_id,
        name=map_name or f"map_{map_id}",
        filesize=0,
        validated=False,
        difficulty=0,
        created_on=now,
        updated_on=now,
        approved_by_steamid64=0,
        synced_at=now,
    )
    session.add(map_obj)
    return map_obj


async def _ensure_server(
    *,
    session: AsyncSession,
    server_id: int,
    server_name: str,
) -> ServerGlobalapi:
    server = await crud.get_server_globalapi_by_id(session=session, id=server_id)
    if server is not None:
        if server_name and not server.name:
            server.name = server_name
            server.synced_at = get_datetime_utc()
            session.add(server)
        return server

    now = get_datetime_utc()
    server = ServerGlobalapi(
        id=server_id,
        port=27015,
        ip=None,
        name=server_name or f"server_{server_id}",
        owner_steamid64=0,
        approval_status=0,
        approved_by_steamid64=0,
        created_on=now,
        updated_on=now,
        synced_at=now,
    )
    session.add(server)
    return server


async def _upsert_record(
    *,
    session: AsyncSession,
    payload: dict[str, Any],
) -> tuple[uuid.UUID, bool, bool]:
    record_id = _parse_int(payload.get("id"), field_name="id")
    steamid64 = _parse_int(payload.get("steamid64"), field_name="steamid64")
    server_id = _parse_int(payload.get("server_id"), field_name="server_id")
    map_id = _parse_int(payload.get("map_id"), field_name="map_id")
    stage = _parse_int(payload.get("stage", 0), field_name="stage")
    mode_name = _parse_string(payload.get("mode"))
    if not mode_name:
        raise ValueError("Missing mode")

    mode = await crud.get_mode_by_name(session=session, mode_name=mode_name)
    if mode is None:
        raise ValueError(f"Unknown mode {mode_name}")

    points = _parse_int(payload.get("points", 0), field_name="points")
    if not 0 <= points <= 1000:
        raise ValueError("Points out of range")

    created_on = _normalize_datetime(payload.get("created_on"))
    updated_on = _normalize_datetime(payload.get("updated_on"))
    record_time = _parse_decimal(payload.get("time"), field_name="time")
    teleports = _parse_int(payload.get("teleports", 0), field_name="teleports")
    updated_by = _parse_int(payload.get("updated_by", 0), field_name="updated_by")
    replay_id = _parse_optional_int(payload.get("replay_id"))

    await _ensure_player(
        session=session,
        steamid64=steamid64,
        player_name=_parse_string(payload.get("player_name")),
        created_on=created_on,
    )
    await _ensure_map(
        session=session,
        map_id=map_id,
        map_name=_parse_string(payload.get("map_name")),
    )
    await _ensure_server(
        session=session,
        server_id=server_id,
        server_name=_parse_string(payload.get("server_name")),
    )

    record, created, updated = await crud.upsert_record(
        session=session,
        record_id=record_id,
        record_uuid=None,
        steamid64=steamid64,
        server_id=server_id,
        mode_id=mode.id,
        map_id=map_id,
        stage=stage,
        time_seconds=record_time,
        teleports=teleports,
        points=points,
        created_on=created_on,
        updated_on=updated_on,
        updated_by=updated_by,
        replay_id=replay_id,
        is_valid=True,
    )
    return record.uuid, created, updated


async def sync_records_from_globalapi(*, session: AsyncSession) -> GlobalApiSyncResult:
    state = await _get_or_create_records_sync_state(session=session)
    max_record_id = await crud.get_max_record_globalapi_id(session=session)
    cursor = (
        state.cursor
        if state.cursor is not None
        else max(max_record_id or 0, DEFAULT_RECORD_START_ID)
    )

    processed = 0
    created = 0
    updated = 0
    errors = 0

    logger.info(
        "Starting GlobalAPI records sync from cursor=%s (stored_cursor=%s, local_max_record_id=%s)",
        cursor,
        state.cursor,
        max_record_id,
    )

    async with httpx.AsyncClient(timeout=settings.GLOBALAPI_TIMEOUT_SECONDS) as client:
        while True:
            logger.debug("Fetching GlobalAPI record record_id=%s", cursor)
            fetch_result = await _fetch_record_with_retry(client=client, record_id=cursor)
            if fetch_result.kind == "record":
                hydrated_payload = await _hydrate_main_stage_points_from_top(
                    client=client,
                    payload=fetch_result.payload or {},
                )
                try:
                    record_uuid, row_created, row_updated = await _upsert_record(
                        session=session,
                        payload=hydrated_payload,
                    )
                except ValueError as exc:
                    logger.warning(
                        "Skipping malformed GlobalAPI record record_id=%s: %s",
                        cursor,
                        exc,
                    )
                    errors += 1
                    state.cursor = cursor + 1
                    session.add(state)
                    await session.commit()
                    cursor += 1
                    continue

                processed += 1
                created += int(row_created)
                updated += int(row_updated)
                sync_action = "created" if row_created else "updated"
                logger.debug(
                    "Synced GlobalAPI record record_id=%s action=%s steamid64=%s map_id=%s server_id=%s points=%s uuid=%s",
                    hydrated_payload.get("id"),
                    sync_action,
                    hydrated_payload.get("steamid64"),
                    hydrated_payload.get("map_id"),
                    hydrated_payload.get("server_id"),
                    hydrated_payload.get("points"),
                    record_uuid,
                )
                state.cursor = cursor + 1
                session.add(state)
                await crud.notify_recent_record_updated(
                    session=session,
                    record_uuid=record_uuid,
                )
                await session.commit()
                cursor += 1
                continue

            logger.debug(
                "GlobalAPI record record_id=%s not found; probing next %s ids",
                cursor,
                NULL_PROBE_WINDOW,
            )
            await asyncio.sleep(NULL_SLEEP_SECONDS)
            probe_success = False
            for probe_id in range(cursor + 1, cursor + NULL_PROBE_WINDOW + 1):
                logger.debug(
                    "Probing GlobalAPI record record_id=%s after missing cursor=%s",
                    probe_id,
                    cursor,
                )
                probe_result = await _fetch_record_with_retry(
                    client=client,
                    record_id=probe_id,
                )
                if probe_result.kind != "record":
                    continue
                hydrated_payload = await _hydrate_main_stage_points_from_top(
                    client=client,
                    payload=probe_result.payload or {},
                )
                try:
                    record_uuid, row_created, row_updated = await _upsert_record(
                        session=session,
                        payload=hydrated_payload,
                    )
                except ValueError as exc:
                    logger.warning(
                        "Skipping malformed probed GlobalAPI record record_id=%s: %s",
                        probe_id,
                        exc,
                    )
                    errors += 1
                    state.cursor = probe_id + 1
                    session.add(state)
                    await session.commit()
                    cursor = probe_id + 1
                    probe_success = True
                    break

                processed += 1
                created += int(row_created)
                updated += int(row_updated)
                sync_action = "created" if row_created else "updated"
                logger.debug(
                    "Synced probed GlobalAPI record record_id=%s action=%s steamid64=%s map_id=%s server_id=%s points=%s uuid=%s",
                    hydrated_payload.get("id"),
                    sync_action,
                    hydrated_payload.get("steamid64"),
                    hydrated_payload.get("map_id"),
                    hydrated_payload.get("server_id"),
                    hydrated_payload.get("points"),
                    record_uuid,
                )
                state.cursor = probe_id + 1
                session.add(state)
                await crud.notify_recent_record_updated(
                    session=session,
                    record_uuid=record_uuid,
                )
                await session.commit()
                cursor = probe_id + 1
                probe_success = True
                break

            if probe_success:
                continue

            state.cursor = cursor
            session.add(state)
            await session.commit()
            result = GlobalApiSyncResult(
                processed=processed,
                created=created,
                updated=updated,
                errors=errors,
            )
            logger.info(
                "Finished GlobalAPI records sync at cursor=%s processed=%s created=%s updated=%s errors=%s warnings=%s",
                cursor,
                result.processed,
                result.created,
                result.updated,
                result.errors,
                result.warnings,
            )
            return result
