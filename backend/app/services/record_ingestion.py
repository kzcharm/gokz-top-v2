"""Transactional native record acceptance, independent of GlobalAPI availability."""

import asyncio
import hashlib
import json
import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, text, true
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as PoolTimeout
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.crud.ban import get_newest_active_ban_for_player, not_active_ban_exists_clause
from app.crud.leaderboard_player import rebuild_leaderboard_players_for_keys
from app.crud.record import notify_recent_record_updated, upsert_record
from app.models import (
    Map,
    MapCourse,
    Mode,
    ModeScope,
    Player,
    Record,
    RecordSourceClaim,
    RecordType,
    RecordUploadReceipt,
    RecordUuidAlias,
    Server,
    ServerGroup,
    ServerGroupStatus,
    ServerStatus,
    generate_uuid7,
    get_datetime_utc,
    mode_scope_modes,
)
from app.models.record_upload import RecordCheck, RecordFinish
from app.services.record_replay_policy import (
    ReplayBucketResult,
    effective_record_filter_mode,
    qualifies_for_run_replay,
)
from app.services.record_submission_policy import (
    available_record_filter_modes,
    mode_version_supported,
)


async def identity_lock(
    session: AsyncSession, identity: str, *, wait: bool = True
) -> None:
    # Stable across processes; never use Python's randomized hash().
    key = int.from_bytes(
        hashlib.sha256(identity.encode()).digest()[:8], "big", signed=True
    )
    await session.execute(text("SET LOCAL lock_timeout = '5s'"))
    if wait:
        await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
    else:
        from app.services.record_transactions import RecordLockBusy

        acquired = await session.execute(
            text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": key}
        )
        if not acquired.scalar_one():
            raise RecordLockBusy(identity)


async def resolve_upload_server(
    session: AsyncSession, group: ServerGroup, identity: uuid.UUID | str
) -> Server:
    if isinstance(identity, uuid.UUID):
        server = await session.get(Server, identity)
    else:
        server = (
            await session.exec(select(Server).where(Server.steamid64 == identity))
        ).first()
        if server is None:
            raise HTTPException(
                503,
                "Waiting for the authenticated server heartbeat",
                headers={"Retry-After": "5"},
            )
    if server is None or server.group_id != group.id:
        raise HTTPException(403, "Server does not belong to this server group")
    return server


async def check_record(
    session: AsyncSession, group: ServerGroup, payload: RecordCheck
) -> tuple[dict[str, Any], Map | None]:
    server = await resolve_upload_server(session, group, payload.server_id)
    map_obj = (
        await session.exec(select(Map).where(Map.name == payload.map_name))
    ).first()
    mode = (
        await session.exec(select(Mode).where(Mode.name_short == payload.mode))
    ).first()
    course = (
        (
            await session.exec(
                select(MapCourse).where(
                    MapCourse.map_id == map_obj.id, MapCourse.stage == payload.stage
                )
            )
        ).first()
        if map_obj
        else None
    )
    effective_mode = effective_record_filter_mode(payload.mode)
    filter_modes = (
        await available_record_filter_modes(
            session,
            map_id=map_obj.id,
            stage=payload.stage,
            tickrate=payload.tickrate,
            teleports=payload.teleports if isinstance(payload, RecordFinish) else None,
        )
        if map_obj and course
        else set()
    )
    ban = await get_newest_active_ban_for_player(
        session=session, steamid64=payload.steamid64
    )
    checks = {
        "authentication": True,
        "server": server.status == ServerStatus.ENABLED,
        "group": group.status == ServerGroupStatus.VALIDATED,
        "map": bool(
            map_obj and map_obj.validated and map_obj.filesize == payload.bsp_size
        ),
        "course": course is not None,
        "filter": effective_mode in filter_modes,
        "mode": mode_version_supported(
            submitted=payload.mode_version,
            minimum=mode.latest_version if mode else None,
        ),
        "player": ban is None,
        "integrity": payload.integrity.valid,
    }
    return {
        "eligible": all(checks.values()),
        "checks": checks,
        "server_id": str(server.id),
        "effective_filter_mode": effective_mode.value,
        "required_mode_version": mode.latest_version if mode else None,
    }, map_obj


async def replay_buckets(
    session: AsyncSession,
    payload: RecordFinish,
    map_id: int,
    exclude_uuid: uuid.UUID | None = None,
) -> list[ReplayBucketResult]:
    buckets = []
    for scope in (
        ModeScope.OVR,
        ModeScope(effective_record_filter_mode(payload.mode).value),
    ):
        for record_type in RecordType:
            if record_type.is_pro and payload.teleports:
                continue
            statement = select(Record.steamid64, func.min(Record.time)).where(
                Record.map_id == map_id,
                Record.stage == payload.stage,
                col(Record.mode).in_(mode_scope_modes(scope)),
                col(Record.is_valid) == true(),
                not_active_ban_exists_clause(steamid64_column=col(Record.steamid64)),
            )
            if exclude_uuid is not None:
                statement = statement.where(Record.uuid != exclude_uuid)
            if record_type.is_pro:
                statement = statement.where(Record.teleports == 0)
            bests = dict(
                (await session.exec(statement.group_by(col(Record.steamid64)))).all()
            )
            buckets.append(
                ReplayBucketResult(
                    scope=scope,
                    type=record_type,
                    previous_pb=bests.get(payload.steamid64),
                    previous_wr=min(bests.values(), default=None),
                    rank=1
                    + sum(
                        time < payload.time
                        for player, time in bests.items()
                        if player != payload.steamid64
                    ),
                )
            )
    return buckets


async def _accept_record(
    session: AsyncSession, group: ServerGroup, payload: RecordFinish, key: str
) -> dict[str, Any]:
    if not key or len(key) > 128:
        raise HTTPException(422, "Idempotency-Key must contain 1 to 128 characters")
    # Authenticate ownership before returning any existing receipt, even after key rotation.
    server = await resolve_upload_server(session, group, payload.server_id)
    body = payload.model_dump(mode="json")
    digest = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    await identity_lock(session, f"receipt:{server.id}:{key}")
    receipt = (
        await session.exec(
            select(RecordUploadReceipt).where(
                RecordUploadReceipt.server_id == server.id,
                RecordUploadReceipt.idempotency_key == key,
            )
        )
    ).first()
    if receipt:
        if receipt.payload_hash != digest:
            raise HTTPException(
                409, "Idempotency key was already used with a different finish"
            )
        return {**receipt.result, "record_uuid": str(receipt.record_uuid)}
    result, map_obj = await check_record(session, group, payload)
    if map_obj is None or result["required_mode_version"] is None:
        raise HTTPException(
            503,
            "Map or mode configuration is not available yet",
            headers={"Retry-After": "60"},
        )
    if not result["eligible"]:
        raise HTTPException(422, result)
    if payload.finished_at > get_datetime_utc() + timedelta(minutes=5):
        raise HTTPException(422, "Finish timestamp is in the future")
    canonical = payload.record_uuid or generate_uuid7(timestamp=payload.finished_at)
    await identity_lock(session, f"uuid:{canonical}")
    existing_record = await session.get(Record, canonical)
    existing_alias = await session.get(RecordUuidAlias, canonical)
    if existing_record is not None or existing_alias is not None:
        raise HTTPException(409, "Record UUID already belongs to another submission")
    # All contenders for a course serialize before reading prior PBs/WRs.
    await identity_lock(session, f"course:{map_obj.id}:{payload.stage}")
    from app.services.record_matching import upstream_match

    received_at = get_datetime_utc()
    preview = Record(
        uuid=canonical,
        steamid64=payload.steamid64,
        native_server_id=server.id,
        mode=payload.mode,
        map_id=map_obj.id,
        stage=payload.stage,
        time=payload.time,
        teleports=payload.teleports,
        created_at=payload.finished_at,
    )
    matched = await upstream_match(session, preview, received_at)
    policy_time = matched.time if matched else payload.time
    policy_payload = payload.model_copy(update={"time": policy_time})
    buckets = await replay_buckets(
        session, policy_payload, map_obj.id, matched.uuid if matched else None
    )
    eligible = qualifies_for_run_replay(
        mode=payload.mode,
        stage=payload.stage,
        teleports=payload.teleports,
        time=policy_time,
        buckets=buckets,
    )
    # Keep uncertain equal-stat runs separate, but freeze the alternative replay
    # decision now in case an explicit upstream identity is verified later.
    alternatives = {}
    candidates = (
        await session.exec(
            select(Record)
            .where(
                Record.steamid64 == payload.steamid64,
                Record.map_id == map_obj.id,
                Record.stage == payload.stage,
                Record.mode == payload.mode,
                Record.time >= payload.time - Decimal("0.001"),
                Record.time <= payload.time,
                Record.teleports == payload.teleports,
                col(Record.id).is_not(None),
                col(Record.native_server_id).is_(None),
            )
            .limit(100)
        )
    ).all()
    for candidate in candidates:
        alternative = await replay_buckets(session, payload, map_obj.id, candidate.uuid)
        alternatives[str(candidate.id)] = qualifies_for_run_replay(
            mode=payload.mode,
            stage=payload.stage,
            teleports=payload.teleports,
            time=payload.time,
            buckets=alternative,
        )
    if alternatives:
        body["_reconciliation_replay_eligibility"] = alternatives

    # Atomic bounds also handle concurrent courses and delayed/offline uploads.
    player_insert = pg_insert(Player).values(
        steamid64=payload.steamid64,
        name=str(payload.steamid64),
        created_at=payload.finished_at,
        last_played_at=payload.finished_at,
    )
    await session.execute(
        player_insert.on_conflict_do_update(
            index_elements=["steamid64"],
            set_={
                "created_at": func.least(Player.created_at, payload.finished_at),
                "last_played_at": func.greatest(
                    Player.last_played_at, payload.finished_at
                ),
            },
        )
    )
    # Refresh any identity-map copy without touching user-managed identity fields.
    player = await session.get(Player, payload.steamid64)
    if player is not None:
        await session.refresh(player)
    record, _, _ = await upsert_record(
        session=session,
        record_id=None,
        record_uuid=canonical,
        steamid64=payload.steamid64,
        server_id=None,
        native_server_id=server.id,
        mode_id=payload.mode.mode_id,
        map_id=map_obj.id,
        stage=payload.stage,
        time_seconds=matched.time if matched else payload.time,
        teleports=payload.teleports,
        points=0,
        created_on=payload.finished_at,
        updated_on=get_datetime_utc(),
        updated_by=0,
        replay_id=None,
        is_valid=True,
        emit_wr_notifications=matched is None,
    )
    # Only changed main-course PBs can affect player ranking totals.
    changed_scopes = {
        bucket.scope.scope_id
        for bucket in buckets
        if bucket.previous_pb is None or policy_time < bucket.previous_pb
    }
    if payload.stage == 0 and changed_scopes:
        await rebuild_leaderboard_players_for_keys(
            session=session,
            keys=[(scope_id, payload.steamid64) for scope_id in sorted(changed_scopes)],
        )
    result = {
        "record_uuid": str(canonical),
        "replay_eligible": eligible,
        "buckets": [
            {
                "scope": b.scope.value,
                "type": b.type.value,
                "rank": b.rank,
                "is_pb": b.previous_pb is None or policy_time < b.previous_pb,
                "is_wr": b.previous_wr is None or policy_time < b.previous_wr,
            }
            for b in buckets
        ],
    }
    session.add(
        RecordUploadReceipt(
            server_id=server.id,
            idempotency_key=key,
            record_uuid=canonical,
            payload_hash=digest,
            payload=body,
            result=result,
            replay_eligible=eligible,
            created_at=received_at,
        )
    )
    await session.flush()
    if matched:
        from app.services.record_reconciliation import merge_records

        source_payload = matched.model_dump(mode="json")
        upstream_id = matched.id
        await merge_records(session, record, matched)
        session.add(
            RecordSourceClaim(
                record_uuid=canonical,
                globalapi_id=upstream_id,
                state="verified",
                source_payload=source_payload,
            )
        )
    for candidate in candidates:
        if matched and candidate.uuid == matched.uuid:
            continue
        session.add(
            RecordSourceClaim(
                record_uuid=canonical,
                globalapi_id=candidate.id,
                state="review",
                detail=(
                    "Equal statistics; explicit upstream identity required"
                    if candidate.time == payload.time
                    else "Legacy precision candidate; explicit upstream identity required"
                ),
            )
        )
    await notify_recent_record_updated(session=session, record_uuid=record.uuid)
    await session.commit()
    return result


async def accept_record(
    session: AsyncSession, group: ServerGroup, payload: RecordFinish, key: str
) -> dict[str, Any]:
    """Retry complete transactions; durable receipts make lost acknowledgements safe."""
    group_id = group.id
    for attempt in range(3):
        try:
            return await _accept_record(session, group, payload, key)
        except PoolTimeout as exc:
            await session.rollback()
            raise HTTPException(
                503, "Records are busy; retry this finish", headers={"Retry-After": "5"}
            ) from exc
        except DBAPIError as exc:
            if getattr(exc.orig, "sqlstate", None) not in {"40P01", "40001", "55P03"}:
                raise
            await session.rollback()
            if attempt == 2:
                raise HTTPException(
                    503,
                    "Records are busy; retry this finish",
                    headers={"Retry-After": "5"},
                ) from exc
            await asyncio.sleep(0.05 * (attempt + 1))
            refreshed = await session.get(ServerGroup, group_id)
            if refreshed is None:
                raise HTTPException(403, "Server group no longer exists")
            group = refreshed
    raise AssertionError("unreachable")
