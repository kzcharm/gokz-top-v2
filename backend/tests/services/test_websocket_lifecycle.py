"""WebSocket isolation, notification dispatch and listener recovery."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import WebSocketDisconnect

from app.api.v1 import player_ws, record_ws, server_ws
from app.models import ModeScope, RecentRecordSnapshotEvent, ServerSnapshotEvent
from app.services import player_steam_profile_events as player_events
from app.services import record_events, server_events

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize(
    "error", [WebSocketDisconnect(), RuntimeError("connection lost")]
)
@pytest.mark.parametrize("route", ["player", "server", "record", "wr"])
async def test_websocket_routes_remove_disconnected_subscribers(
    monkeypatch: pytest.MonkeyPatch,
    route: str,
    error: Exception,
) -> None:
    socket = SimpleNamespace(
        send_json=AsyncMock(), receive=AsyncMock(side_effect=error)
    )
    hub = SimpleNamespace(
        connect=AsyncMock(), disconnect=AsyncMock(), send_snapshot=AsyncMock()
    )
    if route == "player":
        monkeypatch.setattr(player_ws, "player_steam_profile_event_hub", hub)
        await player_ws.websocket_players(socket)
    elif route == "server":
        monkeypatch.setattr(server_ws, "server_event_hub", hub)
        monkeypatch.setattr(
            server_ws,
            "build_server_snapshot_event",
            AsyncMock(
                return_value=ServerSnapshotEvent(type="server.snapshot", servers=[])
            ),
        )
        await server_ws.websocket_servers(socket)
        assert socket.send_json.await_args.args[0]["servers"] == []
    elif route == "record":
        monkeypatch.setattr(record_ws, "recent_record_event_hub", hub)
        snapshot = AsyncMock(return_value=RecentRecordSnapshotEvent(records=[]))
        monkeypatch.setattr(record_ws, "build_recent_record_snapshot_event", snapshot)
        await record_ws.websocket_recent_records(
            socket, scope=ModeScope.KZT, steamid64="76561199022242128"
        )
        assert snapshot.await_args.kwargs["scope"] == ModeScope.KZT
        assert socket.send_json.await_args.args[0]["records"] == []
    else:
        monkeypatch.setattr(record_ws, "recent_wr_event_hub", hub)
        await record_ws.websocket_recent_wrs(
            socket, scope=ModeScope.VNL, map_id=12, tier=3, limit=5
        )
        query = hub.connect.await_args.kwargs["query"]
        assert (query.scope, query.map_id, query.tier, query.limit) == (
            ModeScope.VNL,
            12,
            3,
            5,
        )
    hub.disconnect.assert_awaited_once_with(socket)


async def test_player_event_hub_drops_failed_clients_without_losing_healthy_ones() -> (
    None
):
    class Socket:
        def __init__(self, fail=False):
            self.accept = AsyncMock()
            self.send_json = AsyncMock(
                side_effect=RuntimeError("closed") if fail else None
            )

    hub = player_events.PlayerSteamProfileEventHub()
    good, bad = Socket(), Socket(fail=True)
    await hub.connect(good)
    await hub.connect(bad)
    await hub.broadcast_json({"steamid64": "1"})
    await hub.broadcast_json({"steamid64": "2"})
    assert good.send_json.await_count == 2
    assert bad.send_json.await_count == 1
    await hub.disconnect(good)
    await hub.disconnect(good)
    await hub.broadcast_json({})
    assert good.send_json.await_count == 2


@pytest.mark.parametrize(
    "module,listener",
    [
        (player_events, "listen_for_player_steam_profile_updates"),
        (server_events, "listen_for_server_updates"),
        (record_events, "listen_for_recent_record_updates"),
    ],
)
@pytest.mark.parametrize("failure", [False, True])
async def test_database_notifications_dispatch_and_retry(
    monkeypatch: pytest.MonkeyPatch,
    module,
    listener: str,
    failure: bool,
) -> None:
    statements = []

    class Cursor:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def execute(self, statement):
            statements.append(statement)

    class Connection:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        def cursor(self):
            return Cursor()

        async def notifies(self, **_kwargs):
            if failure:
                raise RuntimeError("database disconnected")
            if module is record_events:
                yield SimpleNamespace(
                    payload="OVR", channel=record_events.RECENT_WR_NOTIFY_CHANNEL
                )
                yield SimpleNamespace(payload="record-id", channel="recent_records")
            else:
                yield SimpleNamespace(payload="invalid")
                yield SimpleNamespace(payload="76561199022242128")
            raise asyncio.CancelledError

    async def connect(*_args, **_kwargs):
        return Connection()

    delays = []

    async def cancel_sleep(delay):
        delays.append(delay)
        raise asyncio.CancelledError

    monkeypatch.setattr(
        module,
        "psycopg",
        SimpleNamespace(AsyncConnection=SimpleNamespace(connect=connect)),
    )
    monkeypatch.setattr(
        module,
        "asyncio",
        SimpleNamespace(sleep=cancel_sleep, CancelledError=asyncio.CancelledError),
    )
    broadcast = AsyncMock()
    wr_broadcast = AsyncMock()
    if module is player_events:
        monkeypatch.setattr(
            module.player_steam_profile_event_hub, "broadcast_json", broadcast
        )
    elif module is server_events:
        monkeypatch.setattr(
            module,
            "build_server_update_event",
            AsyncMock(
                side_effect=[
                    None,
                    ServerSnapshotEvent(type="server.snapshot", servers=[]),
                ]
            ),
        )
        monkeypatch.setattr(module.server_event_hub, "broadcast_json", broadcast)
    else:
        monkeypatch.setattr(
            module.recent_record_event_hub, "broadcast_record_upsert", broadcast
        )
        monkeypatch.setattr(module.recent_wr_event_hub, "broadcast_scope", wr_broadcast)
    assert module._psycopg_database_uri().startswith("postgresql://")
    with pytest.raises(asyncio.CancelledError):
        await getattr(module, listener)()
    assert all(command.startswith("LISTEN ") for command in statements)
    if failure:
        assert delays == [1]
        broadcast.assert_not_awaited()
    else:
        assert broadcast.await_count == 1
        if module is player_events:
            assert broadcast.await_args.args[0]["steamid64"] == "76561199022242128"
        elif module is record_events:
            wr_broadcast.assert_awaited_once_with("OVR")
    await module.stop_listener(None)
    task = asyncio.create_task(asyncio.Event().wait())
    await module.stop_listener(task)
    assert task.cancelled()
