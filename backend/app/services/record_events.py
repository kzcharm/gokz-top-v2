import asyncio
import uuid
from contextlib import suppress
from typing import Any

import psycopg
from fastapi import WebSocket

from app import crud
from app.core.config import settings
from app.core.db import async_session_maker
from app.models import (
    ModeScope,
    RecentRecordListQuery,
    RecentRecordSnapshotEvent,
    RecentRecordUpsertEvent,
)

RECENT_RECORD_SNAPSHOT_LIMIT = 50


class RecentRecordEventHub:
    def __init__(self) -> None:
        self._connections: dict[WebSocket, ModeScope] = {}
        self._lock = asyncio.Lock()

    async def connect(
        self,
        websocket: WebSocket,
        scope: ModeScope = ModeScope.OVR,
    ) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[websocket] = scope

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.pop(websocket, None)

    async def _broadcast_json(self, payloads: dict[WebSocket, dict[str, Any]]) -> None:
        async with self._lock:
            connections = dict(self._connections)

        stale_connections: list[WebSocket] = []
        for connection in connections:
            payload = payloads.get(connection)
            if payload is None:
                continue
            try:
                await connection.send_json(payload)
            except Exception:
                stale_connections.append(connection)

        if not stale_connections:
            return

        async with self._lock:
            for connection in stale_connections:
                self._connections.pop(connection, None)

    async def broadcast_record_upsert(self, record_uuid: str) -> None:
        async with self._lock:
            scopes_by_connection = dict(self._connections)

        payloads: dict[WebSocket, dict[str, Any]] = {}
        for scope in set(scopes_by_connection.values()):
            event = await build_recent_record_upsert_event(record_uuid, scope=scope)
            if event is None:
                continue
            payload = event.model_dump(mode="json")
            for connection, connection_scope in scopes_by_connection.items():
                if connection_scope == scope:
                    payloads[connection] = payload

        await self._broadcast_json(payloads)


recent_record_event_hub = RecentRecordEventHub()


async def build_recent_record_snapshot_event(
    scope: ModeScope = ModeScope.OVR,
) -> RecentRecordSnapshotEvent:
    async with async_session_maker() as session:
        records, _ = await crud.read_recent_records(
            session=session,
            query=RecentRecordListQuery(
                limit=RECENT_RECORD_SNAPSHOT_LIMIT,
                scope=scope,
            ),
        )
    return RecentRecordSnapshotEvent(records=records)


async def build_recent_record_upsert_event(
    record_uuid: str,
    scope: ModeScope = ModeScope.OVR,
) -> RecentRecordUpsertEvent | None:
    try:
        parsed_record_uuid = uuid.UUID(record_uuid)
    except ValueError:
        return None

    async with async_session_maker() as session:
        record = await crud.get_recent_record_public_by_uuid(
            session=session,
            record_uuid=parsed_record_uuid,
            scope=scope,
        )
        if record is None:
            return None
    return RecentRecordUpsertEvent(record=record)


def _psycopg_database_uri() -> str:
    return str(settings.SQLALCHEMY_DATABASE_URI).replace(
        "postgresql+psycopg", "postgresql", 1
    )


async def listen_for_recent_record_updates() -> None:
    while True:
        try:
            async with await psycopg.AsyncConnection.connect(
                _psycopg_database_uri(),
                autocommit=True,
            ) as connection:
                async with connection.cursor() as cursor:
                    await cursor.execute(f"LISTEN {crud.RECENT_RECORD_NOTIFY_CHANNEL}")
                async for notify in connection.notifies(timeout=5.0):
                    await recent_record_event_hub.broadcast_record_upsert(notify.payload)
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
