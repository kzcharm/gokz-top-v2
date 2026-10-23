"""PostgreSQL conflicts retry a complete, fresh rebuild transaction."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import OperationalError

from app.tasks.build import rating

pytestmark = pytest.mark.asyncio


def conflict(sqlstate: str) -> OperationalError:
    error = Exception("database conflict")
    error.sqlstate = sqlstate
    return OperationalError("UPDATE", None, error)


@pytest.mark.parametrize("sqlstate", ["40P01", "40001"])
@pytest.mark.parametrize("phase", ["rebuild", "commit"])
async def test_conflict_retries_fresh_transaction(monkeypatch, sqlstate, phase):
    sessions = []
    closed = []

    @asynccontextmanager
    async def factory():
        session = AsyncMock()
        if not sessions and phase == "commit":
            session.commit.side_effect = conflict(sqlstate)
        sessions.append(session)
        try:
            yield session
        finally:
            closed.append(session)

    operation = AsyncMock(
        side_effect=[conflict(sqlstate), (1, 2)]
        if phase == "rebuild"
        else [(1, 2), (1, 2)]
    )

    async def sleep(delay):
        assert closed == sessions
        assert delay >= 0.5

    monkeypatch.setattr(rating, "async_session_maker", factory)
    monkeypatch.setattr(rating, "rebuild_leaderboard_players_batch", operation)
    monkeypatch.setattr(rating.asyncio, "sleep", sleep)
    assert await rating._rebuild_batch_with_retry(scope_id=0, steamid64s=[1]) == (1, 2)
    assert len(sessions) == 2
    assert operation.await_args.kwargs["session"] is sessions[1]
    sessions[1].commit.assert_awaited_once()


@pytest.mark.parametrize(
    ("sqlstate", "attempts"), [("40P01", 5), ("40001", 5), ("23505", 1)]
)
async def test_retries_are_bounded_and_only_for_conflicts(
    monkeypatch, sqlstate, attempts
):
    sessions = []

    @asynccontextmanager
    async def factory():
        session = AsyncMock()
        sessions.append(session)
        yield session

    operation = AsyncMock(side_effect=conflict(sqlstate))
    sleep = AsyncMock()
    monkeypatch.setattr(rating, "async_session_maker", factory)
    monkeypatch.setattr(rating, "rebuild_leaderboard_players_batch", operation)
    monkeypatch.setattr(rating.asyncio, "sleep", sleep)
    with pytest.raises(OperationalError):
        await rating._rebuild_batch_with_retry(scope_id=0, steamid64s=[1])
    assert len(sessions) == attempts
    assert sleep.await_count == attempts - 1
    for session in sessions:
        session.commit.assert_not_awaited()
