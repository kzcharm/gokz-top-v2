"""Worker scheduling, failure recovery, and lock release contracts."""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import MapFileDistributionSyncResult, ScheduledTaskState
from app.services import (
    jump_replay_cleanup,
    live_streams,
    player_session_timeout,
    server_collector,
    youtube_media,
)
from app.services import map_file_distribution_worker as worker

pytestmark = pytest.mark.asyncio


def use_session(monkeypatch: pytest.MonkeyPatch, module, db: AsyncSession) -> None:
    @asynccontextmanager
    async def session_factory():
        yield db

    monkeypatch.setattr(module, "async_session_maker", session_factory)


async def test_map_worker_schedule_success_failure_and_rerun(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use_session(monkeypatch, worker, db)
    now = datetime(2026, 10, 22, 12, tzinfo=UTC)
    monkeypatch.setattr(worker, "get_datetime_utc", lambda: now)
    monkeypatch.setattr(worker.settings, "MAP_DISTRIBUTION_HOUR_UTC", 13)
    assert not await worker._is_stale(session=db)
    monkeypatch.setattr(worker.settings, "MAP_DISTRIBUTION_HOUR_UTC", 11)
    assert await worker._is_stale(session=db)
    sync = AsyncMock(
        return_value=MapFileDistributionSyncResult(
            processed=7, downloaded=3, uploaded=2, errors=1, warnings=4
        )
    )
    monkeypatch.setattr(worker, "sync_map_files", sync)
    result = await worker.run_map_file_distribution_task(only_stale=True, force=True)
    assert result.processed == 7
    state = await db.get(ScheduledTaskState, worker.TASK_NAME)
    assert state.last_successful_at == now
    assert (
        state.last_processed,
        state.last_created,
        state.last_updated,
        state.last_errors,
        state.last_warnings,
    ) == (7, 3, 2, 1, 4)
    assert await worker.run_map_file_distribution_task(only_stale=True) is None
    assert sync.await_count == 1
    sync.side_effect = RuntimeError("upload failed")
    with pytest.raises(RuntimeError, match="upload failed"):
        await worker.run_map_file_distribution_task(only_stale=False)
    await db.refresh(state)
    assert state.last_error == "upload failed"
    assert state.last_successful_at == now
    sync.side_effect = None
    await worker.run_map_file_distribution_task(only_stale=False)
    assert state.last_error is None
    state.last_successful_at = now - timedelta(days=1)
    assert await worker._is_stale(session=db)


async def test_map_worker_lock_prevents_concurrent_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert worker._psycopg_database_uri().startswith("postgresql://")
    assert worker._advisory_lock_id() == worker._advisory_lock_id()
    sync = AsyncMock()
    monkeypatch.setattr(worker, "sync_map_files", sync)
    async with worker._advisory_lock() as acquired:
        assert acquired
        assert await worker.run_map_file_distribution_task(only_stale=False) is None
    sync.assert_not_awaited()
    async with worker._advisory_lock() as acquired:
        assert acquired


async def test_map_runner_logs_failure_and_stops_cleanly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_iteration(**_kwargs):
        worker._stop_event.set()
        raise RuntimeError("transient failure")

    monkeypatch.setattr(worker, "run_map_file_distribution_task", fail_iteration)
    await worker.run_map_file_distribution_runner()
    assert worker._stop_event is None
    await worker.stop_map_file_distribution_runner(None)
    started = asyncio.Event()

    async def wait_forever():
        started.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(wait_forever())
    await started.wait()
    monkeypatch.setattr(worker, "_stop_event", asyncio.Event())
    await worker.stop_map_file_distribution_runner(task)
    assert task.cancelled()
    assert worker._stop_event.is_set()


@pytest.mark.parametrize(
    ("module", "runner_name", "iteration_name", "stop_name"),
    [
        (
            jump_replay_cleanup,
            "run_jump_replay_cleanup_runner_in_app",
            "cleanup_old_unkept_jump_replays_task_once",
            "stop_jump_replay_cleanup_runner",
        ),
        (
            live_streams,
            "run_live_stream_runner_in_app",
            "refresh_live_streams_once",
            "stop_live_stream_runner",
        ),
        (
            server_collector,
            "run_server_query_collector_in_app",
            "run_server_query_collector",
            "stop_collector",
        ),
        (
            youtube_media,
            "run_media_sync_runner_in_app",
            "sync_youtube_media_once",
            "stop_media_sync_runner",
        ),
        (
            player_session_timeout,
            "run_player_session_timeout_runner_in_app",
            "close_timed_out_player_sessions_once",
            "stop_player_session_timeout_runner",
        ),
    ],
)
@pytest.mark.parametrize("mode", ["success", "locked", "failure"])
async def test_maintenance_workers_release_locks_and_propagate_cancellation(
    monkeypatch: pytest.MonkeyPatch,
    module,
    runner_name: str,
    iteration_name: str,
    stop_name: str,
    mode: str,
) -> None:
    statements = []

    class Cursor:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def execute(self, statement, params):
            statements.append((statement, params))

        async def fetchone(self):
            return (mode != "locked",)

    class Connection:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        def cursor(self):
            return Cursor()

    async def connect(*_args, **_kwargs):
        return Connection()

    async def cancel_sleep(_delay):
        raise asyncio.CancelledError

    iteration = AsyncMock(
        side_effect=RuntimeError("retry later") if mode == "failure" else None
    )
    if module is server_collector and mode == "success":
        iteration.side_effect = asyncio.CancelledError()
    if module is live_streams:
        monkeypatch.setattr(
            module,
            "cleanup_orphaned_live_stream_keyframes_once",
            AsyncMock(side_effect=RuntimeError("cleanup failed")),
        )
    if module is youtube_media:
        monkeypatch.setattr(module, "sync_bilibili_media_once", AsyncMock())
        monkeypatch.setattr(
            module, "refresh_youtube_websub_subscriptions", AsyncMock(return_value=True)
        )
    monkeypatch.setattr(module, iteration_name, iteration)
    monkeypatch.setattr(
        module,
        "psycopg",
        SimpleNamespace(AsyncConnection=SimpleNamespace(connect=connect)),
    )
    monkeypatch.setattr(
        module,
        "asyncio",
        SimpleNamespace(sleep=cancel_sleep, CancelledError=asyncio.CancelledError),
    )
    if module not in (youtube_media, server_collector):
        assert module._psycopg_database_uri().startswith("postgresql://")
    with pytest.raises(asyncio.CancelledError):
        await getattr(module, runner_name)()
    assert "pg_try_advisory_lock" in statements[0][0]
    if mode == "locked":
        iteration.assert_not_awaited()
        assert len(statements) == 1
    else:
        assert iteration.await_count == 1
        assert "pg_advisory_unlock" in statements[-1][0]
    await getattr(module, stop_name)(None)
    task = asyncio.create_task(asyncio.Event().wait())
    await getattr(module, stop_name)(task)
    assert task.cancelled()


async def test_maintenance_operations_use_the_database_transaction(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use_session(monkeypatch, jump_replay_cleanup, db)
    use_session(monkeypatch, player_session_timeout, db)
    cleanup = AsyncMock(return_value=SimpleNamespace(deleted=2))
    timeout = AsyncMock(return_value=3)
    monkeypatch.setattr(
        jump_replay_cleanup, "cleanup_old_unkept_jump_replays_once", cleanup
    )
    monkeypatch.setattr(
        player_session_timeout.crud, "close_timed_out_player_sessions", timeout
    )
    assert (
        await jump_replay_cleanup.cleanup_old_unkept_jump_replays_task_once()
    ).deleted == 2
    assert await player_session_timeout.close_timed_out_player_sessions_once() == 3
    assert timeout.await_args.kwargs["timeout"] == timedelta(
        seconds=player_session_timeout.settings.PLAYER_SESSION_TIMEOUT_SECONDS
    )
