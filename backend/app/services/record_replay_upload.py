import hashlib
import uuid
from typing import Any

import httpx
from fastapi import HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.crud.record import notify_recent_record_updated
from app.models import (
    Map,
    RecordReplay,
    RecordUploadReceipt,
    ServerGroup,
    get_datetime_utc,
)
from app.services import r2_storage
from app.services.record_ingestion import identity_lock
from app.services.record_reconciliation import owned_record
from app.services.run_replay_parser import RunReplayParseError, parse_run_replay_bytes


async def accept_replay(
    session: AsyncSession, group: ServerGroup, record_uuid: uuid.UUID, data: bytes
) -> dict[str, Any]:
    record = await owned_record(session, group, record_uuid)
    await identity_lock(session, f"replay:{record.uuid}")
    checksum = hashlib.sha256(data).hexdigest()
    existing = await session.get(RecordReplay, record.uuid)
    if existing:
        if existing.checksum != checksum:
            raise HTTPException(409, "A different replay is already registered")
        if existing.available:
            return {
                "record_uuid": str(record.uuid),
                "checksum": checksum,
                "available": True,
            }
    receipt = (
        await session.exec(
            select(RecordUploadReceipt).where(
                RecordUploadReceipt.record_uuid == record.uuid
            )
        )
    ).first()
    if not record.is_valid or not receipt or not receipt.replay_eligible:
        raise HTTPException(403, "Record is not eligible for a replay upload")
    try:
        replay = parse_run_replay_bytes(
            data=data, source_name=str(record.uuid), validate_ticks=True
        )
    except RunReplayParseError as exc:
        raise HTTPException(422, str(exc)) from exc
    if abs((replay.recorded_at - record.created_at).total_seconds()) > 60:
        raise HTTPException(422, "Replay timestamp does not match the accepted finish")
    map_obj = await session.get(Map, record.map_id)
    if not map_obj or (
        replay.map_name,
        replay.map_file_size,
        replay.steamid64,
        replay.mode,
        replay.course,
        replay.teleports_used,
    ) != (
        map_obj.name,
        map_obj.filesize,
        record.steamid64,
        record.mode,
        record.stage,
        record.teleports,
    ):
        raise HTTPException(422, "Replay header does not match the accepted record")
    # Support both legacy rounded clients and GlobalAPI-compatible truncation.
    # Match either representation of this exact float, not an arbitrary tolerance.
    if record.time not in {replay.time, replay.truncated_time}:
        raise HTTPException(422, "Replay time does not match the accepted record")
    key = f"replays/runs/{record.uuid}/{checksum}.replay"
    # Immutable object writes are retry-safe. Release the transaction/connection
    # during R2 I/O, then serialize and revalidate the catalog acknowledgement.
    group_id = group.id
    await session.commit()
    try:
        await r2_storage.put_object(
            key=key,
            body=data,
            content_type="application/octet-stream",
            cache_control="public, max-age=31536000, immutable",
        )
    except (httpx.HTTPError, RuntimeError) as exc:
        raise HTTPException(
            503,
            "Replay storage is temporarily unavailable",
            headers={"Retry-After": "30"},
        ) from exc
    refreshed_group = await session.get(ServerGroup, group_id)
    if refreshed_group is None:
        raise HTTPException(403, "Server group no longer exists")
    record = await owned_record(session, refreshed_group, record_uuid)
    await identity_lock(session, f"replay:{record.uuid}")
    await session.refresh(record)
    receipt = (
        await session.exec(
            select(RecordUploadReceipt).where(
                RecordUploadReceipt.record_uuid == record.uuid
            )
        )
    ).first()
    if not record.is_valid or not receipt or not receipt.replay_eligible:
        raise HTTPException(403, "Record is no longer eligible for a replay upload")
    existing = await session.get(RecordReplay, record.uuid, populate_existing=True)
    if existing and existing.checksum != checksum:
        raise HTTPException(409, "A different replay is already registered")
    if existing is None:
        existing = RecordReplay(
            record_uuid=record.uuid,
            storage="r2",
            key=key,
            checksum=checksum,
            size=len(data),
        )
    else:
        existing.storage, existing.key = "r2", key
        existing.available = True
    existing.checked_at = get_datetime_utc()
    session.add(existing)
    await notify_recent_record_updated(session=session, record_uuid=record.uuid)
    await session.commit()
    return {"record_uuid": str(record.uuid), "checksum": checksum, "available": True}
