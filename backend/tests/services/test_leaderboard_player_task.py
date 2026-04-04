from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import delete
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import ScheduledTaskState
from app.services import leaderboard_player_task

pytestmark = pytest.mark.asyncio


async def _clear_task_state(db: AsyncSession) -> None:
    await db.exec(
        delete(ScheduledTaskState).where(
            ScheduledTaskState.task_name == leaderboard_player_task.TASK_NAME
        )
    )
    await db.commit()


async def test_rebuild_changed_leaderboard_players_uses_24h_window_on_first_run(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2099, 4, 4, 12, 0, tzinfo=UTC)
    captured_window_start: datetime | None = None

    async def _fake_load_keys(*, session: AsyncSession, window_start: datetime):
        del session
        nonlocal captured_window_start
        captured_window_start = window_start
        return [(1, 76561198000000001)]

    async def _fake_rebuild(
        *,
        session: AsyncSession,
        keys: list[tuple[int, int]],
    ) -> tuple[int, int]:
        del session
        assert keys == [(1, 76561198000000001)]
        return (1, 0)

    monkeypatch.setattr(leaderboard_player_task, "get_datetime_utc", lambda: now)
    monkeypatch.setattr(
        leaderboard_player_task.crud,
        "load_changed_leaderboard_player_keys",
        _fake_load_keys,
    )
    monkeypatch.setattr(
        leaderboard_player_task.crud,
        "rebuild_leaderboard_players_for_keys",
        _fake_rebuild,
    )

    result = await leaderboard_player_task.rebuild_changed_leaderboard_players(
        session=db
    )

    assert result.processed == 1
    assert result.created == 1
    assert result.updated == 0
    assert captured_window_start == now - timedelta(hours=24)


async def test_rebuild_changed_leaderboard_players_uses_last_successful_window(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _clear_task_state(db)
    now = datetime(2099, 4, 4, 12, 0, tzinfo=UTC)
    expected_window_start = datetime(2099, 4, 4, 10, 30, tzinfo=UTC)
    db.add(
        ScheduledTaskState(
            task_name=leaderboard_player_task.TASK_NAME,
            last_successful_at=expected_window_start,
        )
    )
    await db.commit()

    captured_window_start: datetime | None = None

    async def _fake_load_keys(*, session: AsyncSession, window_start: datetime):
        del session
        nonlocal captured_window_start
        captured_window_start = window_start
        return []

    async def _fake_rebuild(
        *,
        session: AsyncSession,
        keys: list[tuple[int, int]],
    ) -> tuple[int, int]:
        del session
        assert keys == []
        return (0, 0)

    monkeypatch.setattr(leaderboard_player_task, "get_datetime_utc", lambda: now)
    monkeypatch.setattr(
        leaderboard_player_task.crud,
        "load_changed_leaderboard_player_keys",
        _fake_load_keys,
    )
    monkeypatch.setattr(
        leaderboard_player_task.crud,
        "rebuild_leaderboard_players_for_keys",
        _fake_rebuild,
    )

    result = await leaderboard_player_task.rebuild_changed_leaderboard_players(
        session=db
    )

    assert result.processed == 0
    assert captured_window_start == expected_window_start


async def test_run_leaderboard_player_task_skips_when_not_stale(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _clear_task_state(db)
    state = ScheduledTaskState(
        task_name=leaderboard_player_task.TASK_NAME,
        last_successful_at=datetime(2099, 4, 4, 4, 0, tzinfo=UTC),
    )
    db.add(state)
    await db.commit()

    monkeypatch.setattr(
        leaderboard_player_task,
        "get_datetime_utc",
        lambda: datetime(2099, 4, 4, 3, 30, tzinfo=UTC),
    )

    result = await leaderboard_player_task.run_leaderboard_player_task(
        only_stale=True
    )

    assert result is None
