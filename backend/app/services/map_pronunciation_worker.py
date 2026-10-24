import asyncio
import logging
from contextlib import suppress

import psycopg
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.db import async_session_maker
from app.models import (
    MapPronunciation,
    PlayerPronunciation,
    ScheduledTaskState,
    get_datetime_utc,
)
from app.services import pronunciation
from app.services.map_pronunciation import TASK_NAME, is_configured, process_job

logger = logging.getLogger(__name__)
LOCK_ID = 71320619842025


async def process_next_job(*, session: AsyncSession) -> bool:
    state = await session.get(ScheduledTaskState, TASK_NAME)
    if state is not None and state.last_error:
        return False
    row = (
        await session.exec(
            select(MapPronunciation)
            .where(
                col(MapPronunciation.status).in_(["pending", "generating"]),
                MapPronunciation.next_attempt_at <= get_datetime_utc(),
            )
            .order_by(col(MapPronunciation.created_at), col(MapPronunciation.map_id))
            .limit(1)
        )
    ).first()
    player_row = (
        await session.exec(
            select(PlayerPronunciation)
            .where(
                col(PlayerPronunciation.status).in_(["pending", "generating"]),
                PlayerPronunciation.next_attempt_at <= get_datetime_utc(),
            )
            .order_by(
                col(PlayerPronunciation.created_at), col(PlayerPronunciation.steamid64)
            )
            .limit(1)
        )
    ).first()
    if player_row is not None and (
        row is None or player_row.created_at < row.created_at
    ):
        await pronunciation.process_job(session=session, row=player_row)
    elif row is not None:
        await process_job(session=session, row=row)
    else:
        return False
    return True


async def run_map_pronunciation_runner() -> None:
    while True:
        try:
            if is_configured():
                uri = str(settings.SQLALCHEMY_DATABASE_URI).replace(
                    "postgresql+psycopg", "postgresql", 1
                )
                async with await psycopg.AsyncConnection.connect(
                    uri, autocommit=True
                ) as connection:
                    async with connection.cursor() as cursor:
                        await cursor.execute(
                            "SELECT pg_try_advisory_lock(%s)", (LOCK_ID,)
                        )
                        result = await cursor.fetchone()
                    if result and result[0]:
                        # Connection close releases the lock even on cancellation.
                        async with async_session_maker() as session:
                            await process_next_job(session=session)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            # Provider exception messages can contain request data; log only type.
            logger.error("Pronunciation worker failed (%s)", type(error).__name__)
        await asyncio.sleep(settings.MAP_PRONUNCIATION_POLL_SECONDS)


async def stop_map_pronunciation_runner(task: asyncio.Task[None] | None) -> None:
    if task is not None:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
