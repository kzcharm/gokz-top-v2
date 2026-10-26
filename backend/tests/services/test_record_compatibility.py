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
    get_datetime_utc,
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
    pbs = (
        await db.exec(select(RecordPb).where(RecordPb.record_uuid == record.uuid))
    ).all()
    assert pbs and all(pb.time == record.time for pb in pbs)
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
    from app.models import RecordPb

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
    assert not (
        await db.exec(
            select(RecordPb).where(RecordPb.record_uuid == payload.record_uuid)
        )
    ).all()
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


@pytest.mark.asyncio
async def test_pool_timeout_returns_retryable_status_without_holding_transaction(
    db, monkeypatch
):
    from unittest.mock import AsyncMock

    from fastapi import HTTPException
    from sqlalchemy.exc import TimeoutError as PoolTimeout

    from app.services import record_ingestion

    group, _, payload = await setup_finish(db)
    await db.commit()
    operation = AsyncMock(side_effect=PoolTimeout("synthetic exhaustion"))
    monkeypatch.setattr(record_ingestion, "_accept_record", operation)
    with pytest.raises(HTTPException) as error:
        await accept_record(db, group, payload, "pool-busy")
    assert error.value.status_code == 503 and error.value.headers["Retry-After"] == "5"
    assert not db.in_transaction()
    assert operation.await_count == 1


@pytest.mark.asyncio
async def test_receipt_clock_evidence_precedes_scoring(db, monkeypatch):
    from app.services import record_ingestion

    group, _, payload, _ = await fixture(db)
    original = record_ingestion.upsert_record
    started = None

    async def scoring(**kwargs):
        nonlocal started
        started = get_datetime_utc()
        return await original(**kwargs)

    monkeypatch.setattr(record_ingestion, "upsert_record", scoring)
    await accept_record(db, group, payload, "arrival-clock")
    receipt = (await db.exec(select(RecordUploadReceipt))).one()
    assert receipt.created_at <= started


@pytest.mark.asyncio
async def test_second_upstream_claim_preserves_verified_identity_even_with_stale_orm(
    db,
):
    from sqlalchemy.orm.attributes import set_committed_value

    from app.services.record_reconciliation import submit_claim

    group, _, payload, upstream = await fixture(db)
    await accept_record(db, group, payload, "identity-owner")
    await _upsert_record(session=db, payload=upstream)
    await db.commit()
    native = await db.get(Record, payload.record_uuid)
    original_id = native.id
    other_uuid, _, _ = await _upsert_record(
        session=db,
        payload={
            **upstream,
            "id": original_id + 1,
            "created_on": (payload.finished_at + timedelta(seconds=20)).isoformat(),
        },
    )
    await db.commit()
    # Simulate a request that loaded the native row before the winning request
    # committed, without changing the actual database identity.
    set_committed_value(native, "id", None)
    response = await submit_claim(db, group, payload.record_uuid, original_id + 1)
    assert response["state"] == "review"
    assert (await db.get(Record, payload.record_uuid)).id == original_id
    assert (await db.get(Record, other_uuid)).id == original_id + 1
    verified = (
        await db.exec(
            select(RecordSourceClaim).where(RecordSourceClaim.state == "verified")
        )
    ).one()
    assert verified.globalapi_id == original_id


@pytest.mark.asyncio
async def test_explicit_identity_supports_legacy_precision_outside_clock_window(db):
    from app.services.record_reconciliation import submit_claim

    group, _, payload, upstream = await fixture(db)
    payload = payload.model_copy(
        update={"finished_at": payload.finished_at - timedelta(seconds=87)}
    )
    await accept_record(db, group, payload, "legacy-explicit")
    mirror, _, _ = await _upsert_record(session=db, payload=upstream)
    await db.commit()
    assert mirror != payload.record_uuid
    result = await submit_claim(db, group, payload.record_uuid, upstream["id"])
    assert result["state"] == "verified"
    assert (await db.get(Record, payload.record_uuid)).time == Decimal("35.288")


@pytest.mark.asyncio
@pytest.mark.parametrize("sync_first", [False, True])
@pytest.mark.parametrize("delay", [11, 30])
async def test_fast_clock_with_queued_delivery_merges_both_orders(
    db, monkeypatch, sync_first, delay
):
    from app.services import record_ingestion

    group, _, payload, upstream = await fixture(db)
    finished = payload.finished_at
    received = finished + timedelta(seconds=delay)
    monkeypatch.setattr(record_ingestion, "get_datetime_utc", lambda: received)
    payload = payload.model_copy(
        update={
            "finished_at": finished + timedelta(seconds=87),
            "time": Decimal("82.320"),
        }
    )
    upstream["time"] = "82.320"
    old = None
    if sync_first:
        old, _, _ = await _upsert_record(session=db, payload=upstream)
    accepted = await accept_record(db, group, payload, "fast-queued")
    if not sync_first:
        canonical, created, _ = await _upsert_record(session=db, payload=upstream)
        assert canonical == payload.record_uuid and not created
    await db.commit()
    native = await db.get(Record, payload.record_uuid)
    assert native.id == upstream["id"]
    assert native.created_at == payload.finished_at
    assert native.points == 888
    assert (await db.exec(select(RecordUploadReceipt))).one().created_at == received
    assert (await db.exec(select(RecordSourceClaim))).one().state == "verified"
    if old:
        assert (await db.get(RecordUuidAlias, old)).record_uuid == native.uuid
    assert await accept_record(db, group, payload, "fast-queued") == accepted


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        "normal_clock",
        "slow_clock",
        "too_late",
        "short",
        "legacy_short",
        "natives",
        "mirrors",
    ],
)
async def test_queued_clock_fallback_remains_conservative(db, monkeypatch, change):
    from app.services import record_ingestion

    group, _, payload, upstream = await fixture(db)
    finished = payload.finished_at
    received = finished + timedelta(seconds=31 if change == "too_late" else 11)
    monkeypatch.setattr(record_ingestion, "get_datetime_utc", lambda: received)
    clock = {"normal_clock": 11, "slow_clock": -87}.get(change, 87)
    runtime = {"short": "35.000", "legacy_short": "35.001"}.get(change, "82.320")
    payload = payload.model_copy(
        update={
            "finished_at": finished + timedelta(seconds=clock),
            "time": Decimal(runtime),
        }
    )
    upstream["time"] = "35.000" if change == "legacy_short" else runtime
    if change == "mirrors":
        await _upsert_record(session=db, payload=upstream)
        await _upsert_record(session=db, payload={**upstream, "id": 993323})
    await accept_record(db, group, payload, "queued-first")
    if change == "natives":
        # Both receipt windows cover the upstream finish even though receipt
        # times are more than five seconds apart. Neither may win by arrival.
        received += timedelta(seconds=8)
        await accept_record(
            db,
            group,
            payload.model_copy(update={"record_uuid": generate_uuid7()}),
            "queued-second",
        )
    if change != "mirrors":
        canonical, _, _ = await _upsert_record(session=db, payload=upstream)
        assert canonical != payload.record_uuid
    assert (await db.get(Record, payload.record_uuid)).id is None


@pytest.mark.asyncio
async def test_delayed_fast_clock_backfill_uses_same_matching_rules(db, monkeypatch):
    from app.crud.record import upsert_record
    from app.services import record_ingestion

    group, _, payload, upstream = await fixture(db)
    finished = payload.finished_at
    monkeypatch.setattr(
        record_ingestion, "get_datetime_utc", lambda: finished + timedelta(seconds=11)
    )
    payload = payload.model_copy(
        update={
            "finished_at": finished + timedelta(seconds=87),
            "time": Decimal("82.320"),
        }
    )
    await accept_record(db, group, payload, "queued-before-upgrade")
    mirror, _, _ = await upsert_record(
        session=db,
        record_id=upstream["id"],
        record_uuid=generate_uuid7(),
        steamid64=payload.steamid64,
        server_id=upstream["server_id"],
        mode_id=payload.mode.mode_id,
        map_id=982345,
        stage=0,
        time_seconds=Decimal("82.320"),
        teleports=0,
        points=888,
        created_on=finished,
        updated_on=finished,
        updated_by=0,
        replay_id=None,
        is_valid=True,
    )
    receipt = (await db.exec(select(RecordUploadReceipt))).one()
    assert await reconcile_compatible_receipt(db, receipt, apply=False)
    assert (await db.get(Record, payload.record_uuid)).id is None
    old_uuid = mirror.uuid
    assert await reconcile_compatible_receipt(db, receipt, apply=True)
    await db.commit()
    assert (await db.get(RecordUuidAlias, old_uuid)).record_uuid == payload.record_uuid
