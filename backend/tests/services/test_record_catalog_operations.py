from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import httpx
import pytest

from app.core.config import settings
from app.models import RecordReplay
from app.services.record_ingestion import accept_record
from app.services.run_replay_storage import get_run_replay_path, save_run_replay
from tests.services.test_record_ingestion import setup_finish
from tests.utils.run_replay import build_synthetic_run_replay


@pytest.mark.asyncio
async def test_resumable_backfill_and_explicit_reconciliation(
    db, monkeypatch, tmp_path
):
    from app import record_replay_catalog as command

    group, _, payload = await setup_finish(db)
    await accept_record(db, group, payload, "backfill")
    monkeypatch.setattr(settings, "REPLAY_STORAGE_DIR", tmp_path)
    synthetic = build_synthetic_run_replay(map_name=payload.map_name, mode_index=3)
    path = save_run_replay(
        map_name=payload.map_name,
        replay_id=payload.record_uuid,
        replay_bytes=synthetic.replay_bytes,
    )

    @asynccontextmanager
    async def sessions():
        yield db

    monkeypatch.setattr(command, "async_session_maker", sessions)
    await command.run("backfill", 1, None, payload.record_uuid)
    entry = await db.get(RecordReplay, payload.record_uuid)
    assert entry.available and entry.key == str(path.resolve())
    await command.run("backfill", 1, None, payload.record_uuid)
    await command.run("backfill", 1, payload.record_uuid, None)
    path.unlink()
    await command.run("reconcile", 1, None, payload.record_uuid)
    assert not entry.available
    entry.storage = "r2"
    entry.key = "replays/external.replay"
    entry.available = True
    db.add(entry)
    await db.flush()
    monkeypatch.setattr(
        command.r2_storage,
        "build_public_url",
        lambda key: "https://storage.invalid/" + key,
    )
    response = httpx.Response(
        404, request=httpx.Request("HEAD", "https://storage.invalid/object")
    )
    monkeypatch.setattr(httpx.AsyncClient, "head", AsyncMock(return_value=response))
    await command.run("reconcile", 1, None, payload.record_uuid)
    assert not entry.available
    response = httpx.Response(
        200, request=httpx.Request("HEAD", "https://storage.invalid/object")
    )
    monkeypatch.setattr(httpx.AsyncClient, "head", AsyncMock(return_value=response))
    await command.run("reconcile", 1, None, payload.record_uuid)
    assert entry.available


@pytest.mark.asyncio
async def test_operator_inspection_preserves_uncertain_identity(
    db, monkeypatch, caplog
):
    from app import record_identities as command

    group, _, payload = await setup_finish(db)
    await accept_record(db, group, payload, "operator")

    @asynccontextmanager
    async def sessions():
        yield db

    monkeypatch.setattr(command, "async_session_maker", sessions)
    await command.run(payload.record_uuid, 999333, 10)
    await command.run(None, None, 10)
    await command.run(payload.record_uuid, None, 10)
    assert "pending" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("api", [False, True])
async def test_cors_preserves_existing_rules_and_is_repeatable(monkeypatch, api):
    import json
    from app import record_replay_cors as command
    from app.services.r2_storage import R2StorageConfig

    config = R2StorageConfig(
        account_id="account",
        access_key_id="access",
        secret_access_key="secret",
        bucket_name="bucket",
        public_base_url="https://storage.invalid",
    )
    monkeypatch.setattr(command.r2_storage, "get_r2_storage_config", lambda: config)
    monkeypatch.setenv("TEST_CF_TOKEN", "test-token")
    stored = {
        "body": b'<CORSConfiguration xmlns="http://s3.amazonaws.com/doc/2006-03-01/"><CORSRule><AllowedOrigin>https://other.invalid</AllowedOrigin><AllowedMethod>GET</AllowedMethod></CORSRule></CORSConfiguration>'
    }
    rules = [{"allowed": {"origins": ["https://other.invalid"], "methods": ["GET"]}}]
    puts = []

    def handle(request):
        if request.method == "GET":
            return (
                httpx.Response(200, json={"result": {"rules": rules}})
                if api
                else httpx.Response(200, content=stored["body"])
            )
        puts.append(request.content)
        if api:
            rules[:] = json.loads(request.content)["rules"]
            return httpx.Response(200, json={"success": True})
        stored["body"] = request.content
        return httpx.Response(200)

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        command.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handle), **kwargs),
    )
    for _ in range(2):
        if api:
            await command.configure_with_api_token(
                ["https://gokz.top"], "TEST_CF_TOKEN"
            )
        else:
            await command.configure(["https://gokz.top"])
    assert len(puts) == 1
    assert b"https://other.invalid" in puts[0]
    assert b"https://gokz.top" in puts[0]
