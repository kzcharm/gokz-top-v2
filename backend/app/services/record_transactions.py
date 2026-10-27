"""Retry complete record transactions without retaining connections during backoff."""

import asyncio
import random
from collections.abc import Awaitable, Callable

from fastapi import HTTPException
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as PoolTimeout
from sqlmodel.ext.asyncio.session import AsyncSession


class RecordLockBusy(Exception):
    """A record identity is currently being changed by another transaction."""


class RecordTransactionBusy(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            503, "Records are busy; retry this request", headers={"Retry-After": "5"}
        )


async def run_record_transaction[T](
    session: AsyncSession, operation: Callable[[], Awaitable[T]]
) -> T:
    for attempt in range(3):
        try:
            return await operation()
        except PoolTimeout as exc:
            await session.rollback()
            raise RecordTransactionBusy() from exc
        except (RecordLockBusy, DBAPIError) as exc:
            if isinstance(exc, DBAPIError) and getattr(
                exc.orig, "sqlstate", None
            ) not in {"40P01", "40001", "55P03"}:
                raise
            await session.rollback()
            if attempt == 2:
                raise RecordTransactionBusy() from exc
            await asyncio.sleep(random.uniform(0.5, 1.0) * (2**attempt))
    raise AssertionError("unreachable")
