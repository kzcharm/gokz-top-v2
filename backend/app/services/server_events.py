import asyncio
import uuid
from contextlib import suppress
from typing import Any

import psycopg
from fastapi import WebSocket

from app import crud
from app.core.config import settings
from app.core.db import async_session_maker
from app.models import Server, ServerListQuery, ServerSnapshotEvent, ServerUpdateEvent


class ServerEventHub:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(websocket)

    async def broadcast_json(self, payload: dict[str, Any]) -> None:
        async with self._lock:
            connections = list(self._connections)

        stale_connections: list[WebSocket] = []
        for connection in connections:
            try:
                await connection.send_json(payload)
            except Exception:
                stale_connections.append(connection)

        if not stale_connections:
            return

        async with self._lock:
            for connection in stale_connections:
                self._connections.discard(connection)


server_event_hub = ServerEventHub()


async def build_server_snapshot_event() -> ServerSnapshotEvent:
    async with async_session_maker() as session:
        servers, _ = await crud.read_servers(
            session=session,
            query=ServerListQuery(offset=0, limit=1000),
        )
    return ServerSnapshotEvent(
        type="server.snapshot",
        servers=[crud.to_server_public(server=server) for server in servers],
    )


async def build_server_update_event(server_id: str) -> ServerUpdateEvent | None:
    try:
        parsed_server_id = uuid.UUID(server_id)
    except ValueError:
        return None

    async with async_session_maker() as session:
        server = await crud.get_server_by_id(
            session=session,
            server_id=parsed_server_id,
        )
        if server is None:
            return None
    return ServerUpdateEvent(
        type="server.updated",
        server=crud.to_server_public(server=server),
    )


async def broadcast_server_update(server: Server) -> None:
    event = ServerUpdateEvent(
        type="server.updated",
        server=crud.to_server_public(server=server),
    )
    await server_event_hub.broadcast_json(event.model_dump(mode="json"))


def _psycopg_database_uri() -> str:
    return str(settings.SQLALCHEMY_DATABASE_URI).replace(
        "postgresql+psycopg", "postgresql", 1
    )


async def listen_for_server_updates() -> None:
    while True:
        try:
            async with await psycopg.AsyncConnection.connect(
                _psycopg_database_uri(),
                autocommit=True,
            ) as connection:
                async with connection.cursor() as cursor:
                    await cursor.execute(f"LISTEN {crud.SERVER_STATUS_NOTIFY_CHANNEL}")
                async for notify in connection.notifies(timeout=5.0):
                    event = await build_server_update_event(notify.payload)
                    if event is None:
                        continue
                    await server_event_hub.broadcast_json(event.model_dump(mode="json"))
        except asyncio.CancelledError:
            raise
        except Exception:
            await asyncio.sleep(1)


async def stop_listener(task: asyncio.Task[None] | None) -> None:
    if task is None:
        return
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
