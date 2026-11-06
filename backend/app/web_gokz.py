"""Dedicated single-worker host for the two browser rooms and isolated records API."""

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.web_gokz import router
from app.core.config import settings
from app.services.web_gokz import Room, playable_maps, rooms


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    maps = await asyncio.to_thread(playable_maps, settings.WEB_GOKZ_RESOURCES_DIR)
    names = [name for name in ("kz_ominous2", "kz_waterhole") if name in maps]
    names.extend(name for name in maps if name not in names)
    for room_id in (1, 2):
        rooms[room_id] = Room(
            room_id, maps, names[(room_id - 1) % len(names)] if names else ""
        )

    async def clock() -> None:
        while True:
            for room in rooms.values():
                room.tick(time.time())
            await asyncio.sleep(0.1)

    task = asyncio.create_task(clock())
    try:
        yield
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        rooms.clear()


app = FastAPI(title="Web GOKZ", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.all_cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(router, prefix=settings.API_V1_STR)
