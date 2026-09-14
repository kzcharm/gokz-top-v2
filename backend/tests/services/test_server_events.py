from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import ServerRemovedEvent, ServerUpdateEvent
from app.services import server_events
from tests.utils.server import create_server

pytestmark = pytest.mark.asyncio


def _use_test_session(
    monkeypatch: pytest.MonkeyPatch,
    db: AsyncSession,
) -> None:
    @asynccontextmanager
    async def _session() -> AsyncIterator[AsyncSession]:
        yield db

    monkeypatch.setattr(server_events, "async_session_maker", _session)


async def test_server_snapshot_excludes_hidden_servers(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_test_session(monkeypatch, db)
    public_server = await create_server(db)
    hidden_server = await create_server(db, is_public=False)

    event = await server_events.build_server_snapshot_event()

    returned_ids = {server.id for server in event.servers}
    assert public_server.id in returned_ids
    assert hidden_server.id not in returned_ids


async def test_server_update_event_removes_hidden_server(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_test_session(monkeypatch, db)
    hidden_server = await create_server(db, is_public=False)

    event = await server_events.build_server_update_event(str(hidden_server.id))

    assert isinstance(event, ServerRemovedEvent)
    assert event.type == "server.removed"
    assert event.server_id == hidden_server.id


async def test_server_update_event_publishes_visible_server(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_test_session(monkeypatch, db)
    public_server = await create_server(db)

    event = await server_events.build_server_update_event(str(public_server.id))

    assert isinstance(event, ServerUpdateEvent)
    assert event.type == "server.updated"
    assert event.server.id == public_server.id
    assert event.server.is_public is True


async def test_direct_broadcast_skips_hidden_server(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hidden_server = await create_server(db, is_public=False)
    payloads: list[dict[str, object]] = []

    async def _capture_payload(payload: dict[str, object]) -> None:
        payloads.append(payload)

    monkeypatch.setattr(server_events.server_event_hub, "broadcast_json", _capture_payload)

    await server_events.broadcast_server_update(hidden_server)

    assert payloads == []
