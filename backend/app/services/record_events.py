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
    RecentRecordListQuery,
    RecentRecordSnapshotEvent,
    RecentRecordUpsertEvent,
)

RECENT_RECORD_SNAPSHOT_LIMIT = 50


class RecentRecordEventHub:
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


recent_record_event_hub = RecentRecordEventHub()


async def build_recent_record_snapshot_event() -> RecentRecordSnapshotEvent:
    async with async_session_maker() as session:
        records, _ = await crud.read_recent_records(
            session=session,
            query=RecentRecordListQuery(limit=RECENT_RECORD_SNAPSHOT_LIMIT),
        )
    return RecentRecordSnapshotEvent(records=records)


async def build_recent_record_upsert_event(
    record_uuid: str,
) -> RecentRecordUpsertEvent | None:
    try:
        parsed_record_uuid = uuid.UUID(record_uuid)
    except ValueError:
        return None

    async with async_session_maker() as session:
        record = await crud.get_recent_record_public_by_uuid(
            session=session,
            record_uuid=parsed_record_uuid,
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
                    event = await build_recent_record_upsert_event(notify.payload)
                    if event is None:
                        continue
                    await recent_record_event_hub.broadcast_json(
                        event.model_dump(mode="json")
                    )
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
