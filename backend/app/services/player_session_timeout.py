import asyncio
import hashlib
from contextlib import suppress
from datetime import timedelta

import psycopg

from app import crud
from app.core.config import settings
from app.core.db import async_session_maker
from app.models import get_datetime_utc

PLAYER_SESSION_TIMEOUT_LOCK_ID = int.from_bytes(
    hashlib.sha256(b"gokz-top-v2:player-session-timeout").digest()[:8],
    byteorder="big",
    signed=True,
)


def _psycopg_database_uri() -> str:
    return str(settings.SQLALCHEMY_DATABASE_URI).replace(
        "postgresql+psycopg",
        "postgresql",
        1,
    )


async def close_timed_out_player_sessions_once() -> int:
    async with async_session_maker() as session:
        return await crud.close_timed_out_player_sessions(
            session=session,
            now=get_datetime_utc(),
            timeout=timedelta(seconds=settings.PLAYER_SESSION_TIMEOUT_SECONDS),
        )


async def run_player_session_timeout_runner_in_app() -> None:
    while True:
        try:
            async with await psycopg.AsyncConnection.connect(
                _psycopg_database_uri(),
                autocommit=True,
            ) as connection:
                async with connection.cursor() as cursor:
                    await cursor.execute(
                        "SELECT pg_try_advisory_lock(%s)",
                        (PLAYER_SESSION_TIMEOUT_LOCK_ID,),
                    )
                    row = await cursor.fetchone()
                if not row or row[0] is not True:
                    await asyncio.sleep(settings.PLAYER_SESSION_TIMEOUT_POLL_SECONDS)
                    continue

                try:
                    while True:
                        await close_timed_out_player_sessions_once()
                        await asyncio.sleep(
                            settings.PLAYER_SESSION_TIMEOUT_POLL_SECONDS
                        )
                finally:
                    with suppress(Exception):
                        async with connection.cursor() as cursor:
                            await cursor.execute(
                                "SELECT pg_advisory_unlock(%s)",
                                (PLAYER_SESSION_TIMEOUT_LOCK_ID,),
                            )
        except asyncio.CancelledError:
            raise
        except Exception:
            await asyncio.sleep(1)


async def stop_player_session_timeout_runner(
    task: asyncio.Task[None] | None,
) -> None:
    if task is None:
        return
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


__all__ = [
    "PLAYER_SESSION_TIMEOUT_LOCK_ID",
    "close_timed_out_player_sessions_once",
    "run_player_session_timeout_runner_in_app",
    "stop_player_session_timeout_runner",
]
