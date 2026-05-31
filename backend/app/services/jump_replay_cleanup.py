import asyncio
import hashlib
from contextlib import suppress

import psycopg

from app.core.config import settings
from app.core.db import async_session_maker
from app.models import get_datetime_utc
from app.services.jump_replay_retention import (
    JumpReplayCleanupResult,
    cleanup_old_unkept_jump_replays_once,
)

JUMP_REPLAY_CLEANUP_LOCK_ID = int.from_bytes(
    hashlib.sha256(b"gokz-top-v2:jump-replay-cleanup").digest()[:8],
    byteorder="big",
    signed=True,
)


def _psycopg_database_uri() -> str:
    return str(settings.SQLALCHEMY_DATABASE_URI).replace(
        "postgresql+psycopg",
        "postgresql",
        1,
    )


async def cleanup_old_unkept_jump_replays_task_once() -> JumpReplayCleanupResult:
    async with async_session_maker() as session:
        return await cleanup_old_unkept_jump_replays_once(
            session=session,
            now=get_datetime_utc(),
        )


async def run_jump_replay_cleanup_runner_in_app() -> None:
    while True:
        try:
            async with await psycopg.AsyncConnection.connect(
                _psycopg_database_uri(),
                autocommit=True,
            ) as connection:
                async with connection.cursor() as cursor:
                    await cursor.execute(
                        "SELECT pg_try_advisory_lock(%s)",
                        (JUMP_REPLAY_CLEANUP_LOCK_ID,),
                    )
                    row = await cursor.fetchone()
                if not row or row[0] is not True:
                    await asyncio.sleep(settings.JUMP_REPLAY_CLEANUP_POLL_SECONDS)
                    continue

                try:
                    while True:
                        await cleanup_old_unkept_jump_replays_task_once()
                        await asyncio.sleep(settings.JUMP_REPLAY_CLEANUP_POLL_SECONDS)
                finally:
                    with suppress(Exception):
                        async with connection.cursor() as cursor:
                            await cursor.execute(
                                "SELECT pg_advisory_unlock(%s)",
                                (JUMP_REPLAY_CLEANUP_LOCK_ID,),
                            )
        except asyncio.CancelledError:
            raise
        except Exception:
            await asyncio.sleep(1)


async def stop_jump_replay_cleanup_runner(
    task: asyncio.Task[None] | None,
) -> None:
    if task is None:
        return
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


__all__ = [
    "JUMP_REPLAY_CLEANUP_LOCK_ID",
    "cleanup_old_unkept_jump_replays_task_once",
    "run_jump_replay_cleanup_runner_in_app",
    "stop_jump_replay_cleanup_runner",
]
