"""Merge only explicit upstream identities after exact statistics and ownership checks."""

import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy import delete, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import SQLModel, col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import (
    ContentReaction,
    ReactionTargetType,
    Record,
    RecordReplay,
    RecordSourceClaim,
    RecordUploadReceipt,
    RecordUuidAlias,
    Server,
    ServerGlobalapi,
    ServerGroup,
    seconds_to_time_ms,
)
from app.services.record_ingestion import identity_lock


async def owned_record(
    session: AsyncSession, group: ServerGroup, record_uuid: uuid.UUID
) -> Record:
    alias = await session.get(RecordUuidAlias, record_uuid)
    record = await session.get(Record, alias.record_uuid if alias else record_uuid)
    server = (
        await session.get(Server, record.native_server_id)
        if record and record.native_server_id
        else None
    )
    if not record or not server or server.group_id != group.id:
        raise HTTPException(403, "Record does not belong to this server group")
    return record


async def same_source(session: AsyncSession, native: Record, upstream: Record) -> bool:
    if any(
        getattr(native, field) != getattr(upstream, field)
        for field in ("steamid64", "map_id", "stage", "mode", "teleports")
    ):
        return False
    if seconds_to_time_ms(native.time) != seconds_to_time_ms(upstream.time):
        return False
    server = (
        await session.get(Server, native.native_server_id)
        if native.native_server_id
        else None
    )
    global_server = (
        await session.get(ServerGlobalapi, upstream.server_id)
        if upstream.server_id
        else None
    )
    return bool(
        server
        and global_server
        and global_server.group_id == server.group_id
        and global_server.ip == server.ip
        and global_server.port == server.port
    )


async def merge_records(
    session: AsyncSession, native: Record, upstream: Record
) -> None:
    """Keep the supplied native UUID and all previous links, without emitting run events."""
    from app.crud.record import _refresh_record_read_models_for_change

    await identity_lock(session, f"course:{native.map_id}:{native.stage}")
    old, canonical = upstream.uuid, native.uuid
    if old == canonical:
        return
    before = upstream.model_copy(deep=True)
    native.is_valid = native.is_valid and upstream.is_valid
    upstream_id = upstream.id
    upstream.id = None
    await session.flush()
    native.id = upstream_id
    native.server_id = upstream.server_id
    native.replay_id = upstream.replay_id
    # Move FK and historical UUID references transactionally. Cache uniqueness is
    # per bucket; preserve the existing native entry if both ingestion paths ran.
    for table in SQLModel.metadata.tables.values():
        if table.name == "record":
            continue
        for column in table.columns:
            references_record = any(
                fk.target_fullname == "record.uuid" for fk in column.foreign_keys
            )
            historical = column.name in {"previous_record_uuid", "new_record_uuid"}
            if not references_record and not historical:
                continue
            if table.name == "record_replay":
                if await session.get(RecordReplay, canonical):
                    await session.execute(delete(table).where(column == old))
                    continue
            if table.name == "recent_wr_events" and column.name == "record_uuid":
                events = (
                    (await session.execute(table.select().where(column == old)))
                    .mappings()
                    .all()
                )
                for event in events:
                    values = dict(event)
                    values["record_uuid"] = canonical
                    if values.get("previous_record_uuid") == old:
                        values["previous_record_uuid"] = canonical
                    await session.execute(
                        pg_insert(table).values(**values).on_conflict_do_nothing()
                    )
                await session.execute(delete(table).where(column == old))
                continue
            await session.execute(
                update(table).where(column == old).values({column.name: canonical})
            )
    reactions = (
        await session.exec(
            select(ContentReaction).where(
                ContentReaction.content_type == ReactionTargetType.RECENT_WR,
                ContentReaction.content_id == str(old),
            )
        )
    ).all()
    for reaction in reactions:
        values = reaction.model_dump()
        values["content_id"] = str(canonical)
        await session.delete(reaction)
        await session.flush()
        await session.execute(
            pg_insert(ContentReaction).values(**values).on_conflict_do_nothing()
        )
    session.add(RecordUuidAlias(alias=old, record_uuid=canonical))
    await session.delete(upstream)
    await session.flush()
    await _refresh_record_read_models_for_change(
        session=session, before=before, after=native, emit_wr_notifications=False
    )


async def reconcile_claim(session: AsyncSession, claim: RecordSourceClaim) -> bool:
    await identity_lock(session, f"globalapi:{claim.globalapi_id}")
    native = await session.get(Record, claim.record_uuid)
    upstream = (
        await session.exec(select(Record).where(Record.id == claim.globalapi_id))
    ).first()
    if not native or not upstream:
        claim.state = "pending"
        claim.detail = "Waiting for synchronized upstream record"
        session.add(claim)
        return False
    claim.source_payload = upstream.model_dump(mode="json")
    if native.uuid == upstream.uuid:
        claim.state, claim.detail = "verified", ""
    elif upstream.native_server_id is not None or not await same_source(
        session, native, upstream
    ):
        claim.state, claim.detail = (
            "review",
            "Statistics or server ownership do not match",
        )
    else:
        await merge_records(session, native, upstream)
        claim.state, claim.detail = "verified", ""
    if claim.state == "verified":
        receipt = (
            await session.exec(
                select(RecordUploadReceipt).where(
                    RecordUploadReceipt.record_uuid == claim.record_uuid
                )
            )
        ).first()
        if receipt:
            alternatives = receipt.payload.get("_reconciliation_replay_eligibility", {})
            if str(claim.globalapi_id) in alternatives:
                receipt.replay_eligible = bool(alternatives[str(claim.globalapi_id)])
                session.add(receipt)
    session.add(claim)
    return claim.state == "verified"


async def submit_claim(
    session: AsyncSession, group: ServerGroup, record_uuid: uuid.UUID, globalapi_id: int
) -> dict[str, Any]:
    record = await owned_record(session, group, record_uuid)
    await identity_lock(session, f"globalapi:{globalapi_id}")
    claim = (
        await session.exec(
            select(RecordSourceClaim).where(
                RecordSourceClaim.record_uuid == record.uuid,
                RecordSourceClaim.globalapi_id == globalapi_id,
            )
        )
    ).first()
    if claim is None:
        claim = RecordSourceClaim(record_uuid=record.uuid, globalapi_id=globalapi_id)
        session.add(claim)
        await session.flush()
    await reconcile_claim(session, claim)
    result = {
        "record_uuid": str(record.uuid),
        "globalapi_id": globalapi_id,
        "state": claim.state,
        "detail": claim.detail,
    }
    receipt = (
        await session.exec(
            select(RecordUploadReceipt).where(
                RecordUploadReceipt.record_uuid == record.uuid
            )
        )
    ).first()
    result["replay_eligible"] = bool(receipt and receipt.replay_eligible)
    await session.commit()
    return result


async def reconcile_upstream(
    session: AsyncSession, globalapi_id: int
) -> uuid.UUID | None:
    claims = (
        await session.exec(
            select(RecordSourceClaim).where(
                RecordSourceClaim.globalapi_id == globalapi_id,
                col(RecordSourceClaim.state) == "pending",
            )
        )
    ).all()
    canonical = None
    for claim in claims:
        if await reconcile_claim(session, claim):
            canonical = claim.record_uuid
    return canonical


async def resolve_before_sync(
    session: AsyncSession, upstream: Record
) -> uuid.UUID | None:
    """Resolve pending identities before sync can produce duplicate run events."""
    await identity_lock(session, f"globalapi:{upstream.id}")
    claims = (
        await session.exec(
            select(RecordSourceClaim).where(
                RecordSourceClaim.globalapi_id == upstream.id,
                col(RecordSourceClaim.state) == "pending",
            )
        )
    ).all()
    candidates = []
    for claim in claims:
        native = await session.get(Record, claim.record_uuid)
        if native and await same_source(session, native, upstream):
            candidates.append((claim, native))
    if len(candidates) != 1:
        for claim, _ in candidates:
            claim.state, claim.detail = (
                "review",
                "Multiple native records claim this upstream identity",
            )
            session.add(claim)
        return None
    claim, native = candidates[0]
    claim.source_payload = upstream.model_dump(mode="json")
    if native.id is not None and native.id != upstream.id:
        claim.state, claim.detail = (
            "review",
            "Native record already has another upstream identity",
        )
        session.add(claim)
        return None
    existing = (
        await session.exec(select(Record).where(Record.id == upstream.id))
    ).first()
    if existing and existing.uuid != native.uuid:
        return None
    native.id, native.server_id = upstream.id, upstream.server_id
    native.replay_id = upstream.replay_id
    claim.state, claim.detail = "verified", ""
    session.add(native)
    session.add(claim)
    await session.flush()
    return native.uuid
