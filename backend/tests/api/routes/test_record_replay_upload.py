from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api.v1.record_uploads import upload_replay
from app.models import Record, RecordReplay
from app.services import record_replay_upload
from app.services.record_ingestion import accept_record
from tests.services.test_record_ingestion import setup_finish


@pytest.mark.asyncio
async def test_disconnected_replay_upload_keeps_record_and_requests_retry(
    db, monkeypatch
):
    group, _, payload = await setup_finish(db)
    result = await accept_record(db, group, payload, "disconnected-replay")
    record_uuid = UUID(result["record_uuid"])
    receive = AsyncMock(
        side_effect=[
            {"type": "http.request", "body": b"partial replay", "more_body": True},
            {"type": "http.disconnect"},
        ]
    )
    request = Request({"type": "http"}, receive)
    accept = AsyncMock()
    monkeypatch.setattr(record_replay_upload, "accept_replay", accept)
    with pytest.raises(HTTPException) as caught:
        await upload_replay(db, group, record_uuid, request)
    assert caught.value.status_code == 408
    accept.assert_not_awaited()
    assert await db.get(Record, record_uuid) is not None
    assert await db.get(RecordReplay, record_uuid) is None
