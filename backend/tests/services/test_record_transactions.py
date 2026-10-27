"""Reconciliation transaction failures roll back, retry safely, or return 503."""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as PoolTimeout
from sqlmodel import select

from app.models import RecordSourceClaim
from app.services import record_reconciliation, record_transactions
from app.services.record_ingestion import accept_record
from tests.services.test_record_compatibility import fixture


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", ["55P03", "40P01", "40001", "busy", "pool", "other"]
)
@pytest.mark.parametrize("exhausted", [False, True])
async def test_claim_transaction_failure_policy(db, monkeypatch, failure, exhausted):
    group, _, payload, _ = await fixture(db)
    await accept_record(db, group, payload, "claim-retries")
    if failure == "busy":
        error = record_transactions.RecordLockBusy("course")
    elif failure == "pool":
        error = PoolTimeout("test")
    else:
        original = Exception("test")
        original.sqlstate = "23505" if failure == "other" else failure
        error = DBAPIError("test", {}, original)
    operation = AsyncMock(
        side_effect=[error] * 3 if exhausted else [error, {"state": "pending"}]
    )
    monkeypatch.setattr(record_reconciliation, "_submit_claim", operation)

    async def backoff(_delay):
        assert not db.in_transaction()

    monkeypatch.setattr(record_transactions.asyncio, "sleep", backoff)
    if failure == "other":
        with pytest.raises(DBAPIError):
            await record_reconciliation.submit_claim(
                db, group, payload.record_uuid, 993322
            )
        assert operation.await_count == 1
    elif exhausted or failure == "pool":
        with pytest.raises(record_transactions.RecordTransactionBusy) as error:
            await record_reconciliation.submit_claim(
                db, group, payload.record_uuid, 993322
            )
        assert error.value.status_code == 503
        assert error.value.headers["Retry-After"] == "5"
        assert not db.in_transaction()
        assert operation.await_count == (1 if failure == "pool" else 3)
    else:
        assert (
            await record_reconciliation.submit_claim(
                db, group, payload.record_uuid, 993322
            )
        )["state"] == "pending"
        assert operation.await_count == 2


@pytest.mark.asyncio
async def test_retry_rolls_back_partial_claim_before_lost_acknowledgement_retry(
    db, monkeypatch
):
    group, _, payload, upstream = await fixture(db)
    await accept_record(db, group, payload, "partial-claim")
    original = record_reconciliation._submit_claim
    calls = 0

    async def interrupted(session, current_group, record_uuid, globalapi_id):
        nonlocal calls
        calls += 1
        if calls == 1:
            session.add(
                RecordSourceClaim(record_uuid=record_uuid, globalapi_id=globalapi_id)
            )
            await session.flush()
            raise record_transactions.RecordLockBusy("test rollback")
        return await original(session, current_group, record_uuid, globalapi_id)

    monkeypatch.setattr(record_reconciliation, "_submit_claim", interrupted)
    monkeypatch.setattr(record_transactions.asyncio, "sleep", AsyncMock())
    result = await record_reconciliation.submit_claim(
        db, group, payload.record_uuid, upstream["id"]
    )
    assert result["state"] == "pending"
    assert len((await db.exec(select(RecordSourceClaim))).all()) == 1
    assert (
        await record_reconciliation.submit_claim(
            db, group, payload.record_uuid, upstream["id"]
        )
        == result
    )
