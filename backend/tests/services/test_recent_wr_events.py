from unittest.mock import AsyncMock

import pytest

from app.models import ModeScope, RecentWrListQuery, RecentWrSnapshotEvent
from app.services.recent_wr_events import RecentWrEventHub

pytestmark = pytest.mark.asyncio


class FakeWebSocket:
    def __init__(self) -> None:
        self.accepted = False
        self.payloads: list[dict[str, object]] = []

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, payload: dict[str, object]) -> None:
        self.payloads.append(payload)


async def test_recent_wr_hub_sends_filtered_initial_and_update_snapshots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hub = RecentWrEventHub()
    kzt_socket = FakeWebSocket()
    skz_socket = FakeWebSocket()
    kzt_query = RecentWrListQuery(scope=ModeScope.KZT, tier=5)
    skz_query = RecentWrListQuery(scope=ModeScope.SKZ)
    snapshot = RecentWrSnapshotEvent(data=[], count=12)
    build_snapshot = AsyncMock(return_value=snapshot)
    monkeypatch.setattr(hub, "build_snapshot", build_snapshot)

    await hub.connect(kzt_socket, query=kzt_query)  # type: ignore[arg-type]
    await hub.connect(skz_socket, query=skz_query)  # type: ignore[arg-type]
    await hub.send_snapshot(kzt_socket, query=kzt_query)  # type: ignore[arg-type]
    await hub.broadcast_scope("KZT")

    assert kzt_socket.accepted is True
    assert skz_socket.accepted is True
    assert [payload["count"] for payload in kzt_socket.payloads] == [12, 12]
    assert skz_socket.payloads == []
    assert build_snapshot.await_count == 2

    await hub.disconnect(kzt_socket)  # type: ignore[arg-type]
    await hub.broadcast_scope("KZT")
    assert build_snapshot.await_count == 2
