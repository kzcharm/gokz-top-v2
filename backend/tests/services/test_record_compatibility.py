"""Production regressions: legacy precision, grouped endpoints and either arrival order."""

from datetime import timedelta
from decimal import Decimal

import pytest
from sqlmodel import select

from app.models import (
    KZMode,
    Record,
    RecordSourceClaim,
    RecordUploadReceipt,
    RecordUuidAlias,
    ServerGlobalapi,
    generate_uuid7,
)
from app.services.globalapi_record_sync import _upsert_record
from app.services.record_ingestion import accept_record
from app.services.record_reconciliation import reconcile_compatible_receipt
from tests.services.test_record_ingestion import setup_finish


async def fixture(db):
    group, server, payload = await setup_finish(db, KZMode.KZT)
    upstream_server = ServerGlobalapi(
        id=993322,
        name="shared group",
        ip="192.0.2.91",
        port=27016,
        group_id=group.id,
        owner_steamid64=group.owner_steamid64,
    )
    db.add(upstream_server)
    await db.flush()
    upstream = {
        "id": 993322,
        "steamid64": payload.steamid64,
        "server_id": upstream_server.id,
        "map_id": 982345,
        "mode": "kz_timer",
        "stage": 0,
        "time": "35.288",
        "points": 888,
        "teleports": 0,
        "created_on": payload.finished_at.isoformat(),
        "updated_on": payload.finished_at.isoformat(),
    }
    return group, server, payload, upstream


@pytest.mark.asyncio
@pytest.mark.parametrize("sync_first", [False, True])
@pytest.mark.parametrize("fast_clock", [False, True])
async def test_legacy_client_merge_both_orders(db, sync_first, fast_clock):
    from app.models import RecentWrEventCache, RecordPb, RecordReplay

    group, _, payload, upstream = await fixture(db)
    if fast_clock:
        payload = payload.model_copy(
            update={"finished_at": payload.finished_at + timedelta(seconds=87)}
        )
    old = None
    if sync_first:
        old, _, _ = await _upsert_record(
            session=db, payload=upstream, emit_wr_notifications=True
        )
    accepted = await accept_record(db, group, payload, "legacy-finish")
    assert accepted["replay_eligible"]
    event_count = len((await db.exec(select(RecentWrEventCache))).all())
    if not sync_first:
        # A stored replay stays accessible under the supplied canonical UUID.
        db.add(
            RecordReplay(
                record_uuid=payload.record_uuid,
                storage="r2",
                key="immutable/test",
                checksum="a" * 64,
                size=123,
            )
        )
        await db.commit()
        canonical, created, _ = await _upsert_record(session=db, payload=upstream)
        assert canonical == payload.record_uuid and not created
    await db.commit()
    assert len((await db.exec(select(RecentWrEventCache))).all()) == event_count
    record = await db.get(Record, payload.record_uuid)
    assert record.id == upstream["id"] and record.time == Decimal("35.288")
    assert record.points == 888
    assert (
        len(
            (
                await db.exec(
                    select(Record).where(Record.steamid64 == payload.steamid64)
                )
            ).all()
        )
        == 1
    )
    claims = (await db.exec(select(RecordSourceClaim))).all()
    assert len(claims) == 1 and claims[0].state == "verified"
    assert (
        await db.exec(select(RecordPb).where(RecordPb.record_uuid == record.uuid))
    ).all()
    if old:
        assert (await db.get(RecordUuidAlias, old)).record_uuid == record.uuid
    else:
        assert (await db.get(RecordReplay, record.uuid)).key == "immutable/test"
    assert await accept_record(db, group, payload, "legacy-finish") == accepted
    record.is_valid = False
    db.add(record)
    await db.commit()
    await _upsert_record(session=db, payload=upstream)
    assert not (await db.get(Record, record.uuid)).is_valid


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change", ["historical", "different_owner", "precision", "two_finishes"]
)
async def test_compatibility_refuses_uncertain_matches(db, change):
    group, _, payload, upstream = await fixture(db)
    await accept_record(db, group, payload, "first")
    if change == "historical":
        upstream["created_on"] = (payload.finished_at - timedelta(days=1)).isoformat()
    elif change == "different_owner":
        server = await db.get(ServerGlobalapi, upstream["server_id"])
        server.group_id = None
        db.add(server)
        await db.commit()
    elif change == "precision":
        upstream["time"] = "35.287"
    else:
        await accept_record(
            db,
            group,
            payload.model_copy(update={"record_uuid": generate_uuid7()}),
            "second",
        )
    resolved, _, _ = await _upsert_record(session=db, payload=upstream)
    assert resolved != payload.record_uuid
    assert (await db.get(Record, payload.record_uuid)).id is None


@pytest.mark.asyncio
async def test_two_upstream_finishes_are_not_merged(db):
    group, _, payload, upstream = await fixture(db)
    await _upsert_record(session=db, payload=upstream)
    await _upsert_record(session=db, payload={**upstream, "id": 993323})
    await accept_record(db, group, payload, "ambiguous")
    assert (await db.get(Record, payload.record_uuid)).id is None


@pytest.mark.asyncio
async def test_historical_compatibility_backfill_dry_run_and_apply(db):
    from app.crud.record import upsert_record

    group, _, payload, upstream = await fixture(db)
    await accept_record(db, group, payload, "before-upgrade")
    mirror, _, _ = await upsert_record(
        session=db,
        record_id=upstream["id"],
        record_uuid=generate_uuid7(),
        steamid64=payload.steamid64,
        server_id=upstream["server_id"],
        mode_id=payload.mode.mode_id,
        map_id=982345,
        stage=0,
        time_seconds=Decimal(upstream["time"]),
        teleports=0,
        points=1000,
        created_on=payload.finished_at,
        updated_on=payload.finished_at,
        updated_by=0,
        replay_id=None,
        is_valid=False,
    )
    old = mirror.uuid
    receipt = (await db.exec(select(RecordUploadReceipt))).one()
    assert await reconcile_compatible_receipt(db, receipt, apply=False)
    assert (await db.get(Record, payload.record_uuid)).id is None
    assert await reconcile_compatible_receipt(db, receipt, apply=True)
    await db.commit()
    assert not (await db.get(Record, payload.record_uuid)).is_valid
    assert (await db.get(RecordUuidAlias, old)).record_uuid == payload.record_uuid
    assert not await reconcile_compatible_receipt(db, receipt, apply=True)


@pytest.mark.asyncio
async def test_sync_releases_transaction_before_steam_network(db, monkeypatch):
    from app import crud

    _, _, _, upstream = await fixture(db)

    async def fetch(_steamid64):
        assert not db.in_transaction()
        return {}

    monkeypatch.setattr(crud, "_fetch_player_from_steam_api", fetch)
    await _upsert_record(session=db, payload=upstream)


@pytest.mark.asyncio
@pytest.mark.parametrize("exhausted", [False, True])
async def test_transient_transaction_retry_and_busy_response(
    db, monkeypatch, exhausted
):
    from unittest.mock import AsyncMock

    from fastapi import HTTPException
    from sqlalchemy.exc import DBAPIError

    from app.services import record_ingestion

    group, _, payload = await setup_finish(db)
    await db.commit()

    class Deadlock(Exception):
        sqlstate = "40P01"

    failure = DBAPIError("synthetic", {}, Deadlock())
    operation = AsyncMock(
        side_effect=[failure] * 3
        if exhausted
        else [failure, {"record_uuid": str(payload.record_uuid)}]
    )
    monkeypatch.setattr(record_ingestion, "_accept_record", operation)
    if exhausted:
        with pytest.raises(HTTPException) as exc:
            await accept_record(db, group, payload, "retry")
        assert exc.value.status_code == 503 and exc.value.headers["Retry-After"] == "5"
        assert not db.in_transaction()
    else:
        assert (await accept_record(db, group, payload, "retry"))["record_uuid"] == str(
            payload.record_uuid
        )
    assert operation.await_count == (3 if exhausted else 2)


@pytest.mark.asyncio
async def test_short_finishes_require_explicit_identity(db):
    group, _, payload, upstream = await fixture(db)
    payload = payload.model_copy(update={"time": Decimal("2.000")})
    await accept_record(db, group, payload, "rapid")
    canonical, _, _ = await _upsert_record(
        session=db, payload={**upstream, "time": "2.000"}
    )
    assert canonical != payload.record_uuid
