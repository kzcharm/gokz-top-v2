"""Browser downloads resolve metadata before fetching public R2 bytes directly."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from app.api.deps import get_db
from app.api.v1 import replays


@pytest.mark.asyncio
@pytest.mark.parametrize("storage", ["r2", "disk"])
@pytest.mark.parametrize("alias", [False, True])
async def test_replay_url_resolves_catalog_without_storage_probes(
    monkeypatch, storage, alias
):
    canonical = uuid.uuid7()
    requested = uuid.uuid7() if alias else canonical
    record = SimpleNamespace(uuid=canonical)
    replay = SimpleNamespace(
        available=True, storage=storage, key="replays/runs/file.replay"
    )
    session = SimpleNamespace(get=AsyncMock(return_value=replay))
    lookup = AsyncMock(return_value=record)
    monkeypatch.setattr(replays.crud, "get_record_by_uuid", lookup)
    monkeypatch.setattr(
        replays.r2_storage, "build_public_url", lambda key: f"https://r2.example/{key}"
    )
    app = FastAPI()
    app.include_router(replays.router, prefix="/v1")
    app.dependency_overrides[get_db] = lambda: session
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://api.example"
    ) as client:
        response = await client.get(f"/v1/replays/{requested}/url")
    assert response.status_code == 200
    assert response.json() == {
        "url": (
            "https://r2.example/replays/runs/file.replay"
            if storage == "r2"
            else f"https://api.example/v1/replays/{canonical}"
        )
    }
    lookup.assert_awaited_once_with(session=session, record_uuid=requested)
    session.get.assert_awaited_once_with(replays.RecordReplay, canonical)


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["no_record", "no_replay", "unavailable"])
async def test_replay_url_rejects_missing_catalog_entries(monkeypatch, state):
    record = None if state == "no_record" else SimpleNamespace(uuid=uuid.uuid7())
    replay = None if state == "no_replay" else SimpleNamespace(available=False)
    session = SimpleNamespace(get=AsyncMock(return_value=replay))
    monkeypatch.setattr(
        replays.crud, "get_record_by_uuid", AsyncMock(return_value=record)
    )
    app = FastAPI()
    app.include_router(replays.router, prefix="/v1")
    app.dependency_overrides[get_db] = lambda: session
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://api.example"
    ) as client:
        response = await client.get(f"/v1/replays/{uuid.uuid7()}/url")
    assert response.status_code == 404
    assert response.json()["detail"] == (
        "Record not found" if state == "no_record" else "Replay not found"
    )
