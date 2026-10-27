"""Reconcile verified upstream identities and conservative legacy compatibility matches."""

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
    ServerGroup,
)
from app.services.record_ingestion import identity_lock
from app.services.record_transactions import run_record_transaction


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
    from app.services.record_matching import same_owner, statistics_match

    return statistics_match(native, upstream, legacy=True) and await same_owner(
        session, native, upstream
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
    # Both rows can have populated read models. Rebuild if either was valid,
    # and flag the retained UUID's precision correction even when the source
    # row was invalidated before this merge.
    before = Record(
        **{
            **upstream.model_dump(),
            "uuid": canonical,
            "time": native.time,
            "is_valid": native.is_valid or upstream.is_valid,
        }
    )
    native.is_valid = native.is_valid and upstream.is_valid
    upstream_id = upstream.id
    upstream.id = None
    await session.flush()
    native.id = upstream_id
    native.server_id = upstream.server_id
    native.replay_id = upstream.replay_id
    native.time = upstream.time
    native.points = upstream.points
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
    native = await session.get(Record, claim.record_uuid)
    if native:
        await identity_lock(session, f"course:{native.map_id}:{native.stage}")
        # Another request may have linked this UUID while we waited. Refresh
        # the ORM identity map before deciding whether a second claim is safe.
        await session.refresh(native)
    await identity_lock(session, f"globalapi:{claim.globalapi_id}")
    if native and native.id is not None and native.id != claim.globalapi_id:
        claim.state, claim.detail = (
            "review",
            "Native record already has another upstream identity",
        )
        session.add(claim)
        return False
    upstream = (
        await session.exec(select(Record).where(Record.id == claim.globalapi_id))
    ).first()
    if not native or not upstream:
        claim.state = "pending"
        claim.detail = "Waiting for synchronized upstream record"
        session.add(claim)
        return False
    if claim.state != "verified" or claim.source_payload is None:
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
    group_id = group.id

    async def operation() -> dict[str, Any]:
        # Rollbacks expire ORM objects. Reload ownership within every attempt.
        current_group = await session.get(ServerGroup, group_id)
        if current_group is None:
            raise HTTPException(403, "Server group no longer exists")
        return await _submit_claim(session, current_group, record_uuid, globalapi_id)

    return await run_record_transaction(session, operation)


async def _submit_claim(
    session: AsyncSession, group: ServerGroup, record_uuid: uuid.UUID, globalapi_id: int
) -> dict[str, Any]:
    record = await owned_record(session, group, record_uuid)
    await identity_lock(session, f"course:{record.map_id}:{record.stage}", wait=False)
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
    await identity_lock(session, f"course:{upstream.map_id}:{upstream.stage}")
    await identity_lock(session, f"globalapi:{upstream.id}")
    linked = (
        await session.exec(select(Record).where(Record.id == upstream.id))
    ).first()
    if linked and linked.native_server_id is not None:
        # Later upstream refreshes must not resurrect a moderated native run.
        linked.replay_id = upstream.replay_id
        linked.points = upstream.points
        session.add(linked)
        return linked.uuid
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
    if not candidates:
        from app.services.record_matching import native_match

        native = await native_match(session, upstream)
        if native:
            compatible_claim = (
                await session.exec(
                    select(RecordSourceClaim).where(
                        RecordSourceClaim.record_uuid == native.uuid,
                        RecordSourceClaim.globalapi_id == upstream.id,
                    )
                )
            ).first()
            if compatible_claim is None:
                compatible_claim = RecordSourceClaim(
                    record_uuid=native.uuid, globalapi_id=upstream.id
                )
            candidates.append((compatible_claim, native))
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
    before = native.model_copy(deep=True)
    native.id, native.server_id = upstream.id, upstream.server_id
    native.time = upstream.time
    native.points = upstream.points
    native.replay_id = upstream.replay_id
    claim.state, claim.detail = "verified", ""
    session.add(native)
    session.add(claim)
    await session.flush()
    if before.time != native.time:
        from app.crud.record import _refresh_record_read_models_for_change

        await _refresh_record_read_models_for_change(
            session=session, before=before, after=native, emit_wr_notifications=False
        )
    return native.uuid


async def reconcile_compatible_receipt(
    session: AsyncSession, receipt: RecordUploadReceipt, *, apply: bool
) -> bool:
    """Bounded operator backfill uses exactly the live compatibility checks."""
    from app.services.record_matching import upstream_match

    native = await session.get(Record, receipt.record_uuid)
    if not native or native.id is not None:
        return False
    await identity_lock(session, f"course:{native.map_id}:{native.stage}")
    await session.refresh(native)
    if native.id is not None:
        return False
    upstream = await upstream_match(session, native, receipt.created_at)
    if not upstream:
        return False
    if not apply:
        return True
    await identity_lock(session, f"globalapi:{upstream.id}")
    claim = (
        await session.exec(
            select(RecordSourceClaim).where(
                RecordSourceClaim.record_uuid == native.uuid,
                RecordSourceClaim.globalapi_id == upstream.id,
            )
        )
    ).first()
    if claim is None:
        claim = RecordSourceClaim(record_uuid=native.uuid, globalapi_id=upstream.id)
    upstream_id = upstream.id
    claim.source_payload = upstream.model_dump(mode="json")
    await merge_records(session, native, upstream)
    claim.state, claim.detail = "verified", ""
    session.add(claim)
    alternatives = receipt.payload.get("_reconciliation_replay_eligibility", {})
    if str(upstream_id) in alternatives:
        receipt.replay_eligible = bool(alternatives[str(upstream_id)])
        receipt.result = {**receipt.result, "replay_eligible": receipt.replay_eligible}
        session.add(receipt)
    return True
