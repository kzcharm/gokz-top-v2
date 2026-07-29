import asyncio
from contextlib import suppress
from typing import Any

import psycopg
from fastapi import WebSocket

from app.core.config import settings
from app.crud.player import PLAYER_STEAM_PROFILE_NOTIFY_CHANNEL
from app.models import PlayerSteamProfileUpdatedEvent


class PlayerSteamProfileEventHub:
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


player_steam_profile_event_hub = PlayerSteamProfileEventHub()


def _psycopg_database_uri() -> str:
    return str(settings.SQLALCHEMY_DATABASE_URI).replace(
        "postgresql+psycopg", "postgresql", 1
    )


async def listen_for_player_steam_profile_updates() -> None:
    while True:
        try:
            async with await psycopg.AsyncConnection.connect(
                _psycopg_database_uri(),
                autocommit=True,
            ) as connection:
                async with connection.cursor() as cursor:
                    await cursor.execute(
                        f"LISTEN {PLAYER_STEAM_PROFILE_NOTIFY_CHANNEL}"
                    )
                async for notify in connection.notifies(timeout=5.0):
                    try:
                        steamid64 = int(notify.payload)
                    except ValueError:
                        continue
                    event = PlayerSteamProfileUpdatedEvent(
                        steamid64=str(steamid64),
                    )
                    await player_steam_profile_event_hub.broadcast_json(
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
