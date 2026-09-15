import asyncio
from typing import Any

from fastapi import WebSocket

from app.core.db import async_session_maker
from app.crud.recent_wr import read_recent_wrs, recent_wr_backfill_is_ready
from app.models import RecentWrListQuery, RecentWrSnapshotEvent


class RecentWrEventHub:
    def __init__(self) -> None:
        self._connections: dict[WebSocket, RecentWrListQuery] = {}
        self._lock = asyncio.Lock()

    async def connect(
        self,
        websocket: WebSocket,
        *,
        query: RecentWrListQuery,
    ) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[websocket] = query

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.pop(websocket, None)

    async def build_snapshot(
        self,
        *,
        query: RecentWrListQuery,
    ) -> RecentWrSnapshotEvent:
        async with async_session_maker() as session:
            if not await recent_wr_backfill_is_ready(session=session):
                return RecentWrSnapshotEvent(data=[], count=0)
            data, count = await read_recent_wrs(session=session, query=query)
        return RecentWrSnapshotEvent(data=data, count=count)

    async def send_snapshot(
        self,
        websocket: WebSocket,
        *,
        query: RecentWrListQuery,
    ) -> None:
        snapshot = await self.build_snapshot(query=query)
        await websocket.send_json(snapshot.model_dump(mode="json"))

    async def broadcast_scope(self, scope: str) -> None:
        async with self._lock:
            connections = dict(self._connections)

        snapshots: dict[str, dict[str, Any]] = {}
        stale: list[WebSocket] = []
        for connection, query in connections.items():
            if query.scope.value != scope:
                continue
            cache_key = query.model_dump_json()
            payload = snapshots.get(cache_key)
            if payload is None:
                snapshot = await self.build_snapshot(query=query)
                payload = snapshot.model_dump(mode="json")
                snapshots[cache_key] = payload
            try:
                await connection.send_json(payload)
            except Exception:
                stale.append(connection)

        if stale:
            async with self._lock:
                for connection in stale:
                    self._connections.pop(connection, None)


recent_wr_event_hub = RecentWrEventHub()
