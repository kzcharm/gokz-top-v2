import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import delete
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import GlobalApiSyncResult, GlobalApiSyncState, get_datetime_utc
from app.services import globalapi_sync

pytestmark = pytest.mark.asyncio


def _patch_session_maker(
    *,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @asynccontextmanager
    async def _session_maker():
        yield db

    monkeypatch.setattr(globalapi_sync, "async_session_maker", _session_maker)


async def test_run_globalapi_sync_tasks_runs_stale_tasks_in_sequence(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_session_maker(db=db, monkeypatch=monkeypatch)
    order: list[str] = []

    async def _first(*, session: AsyncSession) -> GlobalApiSyncResult:
        del session
        order.append("first")
        return GlobalApiSyncResult(processed=1, created=1, updated=0, errors=0)

    async def _second(*, session: AsyncSession) -> GlobalApiSyncResult:
        del session
        order.append("second")
        return GlobalApiSyncResult(processed=1, created=0, updated=1, errors=0)

    monkeypatch.setattr(
        globalapi_sync,
        "GLOBALAPI_SYNC_TASKS",
        (
            globalapi_sync.GlobalApiSyncTask("first", 86_400, _first),
            globalapi_sync.GlobalApiSyncTask("second", 86_400, _second),
        ),
    )

    results = await globalapi_sync.run_globalapi_sync_tasks(only_stale=True)

    assert order == ["first", "second"]
    assert set(results) == {"first", "second"}


async def test_run_globalapi_sync_tasks_skips_fresh_tasks(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_session_maker(db=db, monkeypatch=monkeypatch)
    calls = 0

    async def _task(*, session: AsyncSession) -> GlobalApiSyncResult:
        nonlocal calls
        del session
        calls += 1
        return GlobalApiSyncResult(processed=1, created=0, updated=1, errors=0)

    monkeypatch.setattr(
        globalapi_sync,
        "GLOBALAPI_SYNC_TASKS",
        (globalapi_sync.GlobalApiSyncTask("fresh", 86_400, _task),),
    )

    await globalapi_sync.run_globalapi_sync_tasks(only_stale=True)
    assert calls == 1

    await globalapi_sync.run_globalapi_sync_tasks(only_stale=True)
    assert calls == 1


async def test_run_globalapi_sync_tasks_prevents_overlap(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_session_maker(db=db, monkeypatch=monkeypatch)
    started = asyncio.Event()
    release = asyncio.Event()

    async def _slow_task(*, session: AsyncSession) -> GlobalApiSyncResult:
        del session
        started.set()
        await release.wait()
        return GlobalApiSyncResult(processed=1, created=0, updated=0, errors=0)

    monkeypatch.setattr(
        globalapi_sync,
        "GLOBALAPI_SYNC_TASKS",
        (globalapi_sync.GlobalApiSyncTask("slow", 0, _slow_task),),
    )

    first_run = asyncio.create_task(
        globalapi_sync.run_globalapi_sync_tasks(only_stale=False)
    )
    await started.wait()

    overlapping_result = await globalapi_sync.run_globalapi_sync_tasks(only_stale=False)
    assert overlapping_result == {}

    release.set()
    await first_run


async def test_stop_globalapi_sync_runner_stops_background_loop(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_session_maker(db=db, monkeypatch=monkeypatch)
    executed = asyncio.Event()

    async def _task(*, session: AsyncSession) -> GlobalApiSyncResult:
        del session
        executed.set()
        return GlobalApiSyncResult(processed=1, created=0, updated=0, errors=0)

    monkeypatch.setattr(
        globalapi_sync,
        "GLOBALAPI_SYNC_TASKS",
        (globalapi_sync.GlobalApiSyncTask("runner", 0, _task),),
    )
    monkeypatch.setattr(
        globalapi_sync.settings,
        "GLOBALAPI_SYNC_RUNNER_POLL_SECONDS",
        3600,
    )

    runner_task = asyncio.create_task(globalapi_sync.run_globalapi_sync_runner_in_app())
    await executed.wait()

    await globalapi_sync.stop_globalapi_sync_runner(runner_task)
    assert runner_task.done()


async def test_run_globalapi_sync_tasks_records_state(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_session_maker(db=db, monkeypatch=monkeypatch)
    async def _task(*, session: AsyncSession) -> GlobalApiSyncResult:
        del session
        return GlobalApiSyncResult(
            processed=5,
            created=2,
            updated=3,
            errors=1,
            warnings=4,
        )

    monkeypatch.setattr(
        globalapi_sync,
        "GLOBALAPI_SYNC_TASKS",
        (globalapi_sync.GlobalApiSyncTask("stateful", 86_400, _task),),
    )

    await globalapi_sync.run_globalapi_sync_tasks(only_stale=False)

    state = await db.get(GlobalApiSyncState, "stateful")
    assert state is not None
    assert state.last_started_at is not None
    assert state.last_completed_at is not None
    assert state.last_successful_at is not None
    assert state.last_completed_at >= state.last_started_at
    assert state.last_successful_at >= get_datetime_utc() - timedelta(minutes=1)
    assert state.last_processed == 5
    assert state.last_created == 2
    assert state.last_updated == 3
    assert state.last_errors == 1
    assert state.last_warnings == 4


async def test_run_globalapi_sync_tasks_honors_per_task_staleness(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_session_maker(db=db, monkeypatch=monkeypatch)
    calls: list[str] = []

    await db.exec(delete(GlobalApiSyncState).where(GlobalApiSyncState.task_name == "servers"))
    await db.commit()

    fresh_server = GlobalApiSyncState(
        task_name="servers",
        last_successful_at=get_datetime_utc(),
    )
    db.add(fresh_server)
    await db.commit()

    async def _servers(*, session: AsyncSession) -> GlobalApiSyncResult:
        del session
        calls.append("servers")
        return GlobalApiSyncResult(processed=1, created=0, updated=1, errors=0)

    async def _records(*, session: AsyncSession) -> GlobalApiSyncResult:
        del session
        calls.append("records")
        return GlobalApiSyncResult(processed=1, created=1, updated=0, errors=0)

    monkeypatch.setattr(
        globalapi_sync,
        "GLOBALAPI_SYNC_TASKS",
        (
            globalapi_sync.GlobalApiSyncTask("servers", 86_400, _servers),
            globalapi_sync.GlobalApiSyncTask("records", 0, _records),
        ),
    )

    results = await globalapi_sync.run_globalapi_sync_tasks(only_stale=True)

    assert calls == ["records"]
    assert set(results) == {"records"}


async def test_run_globalapi_sync_tasks_records_state_for_record_filters(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_session_maker(db=db, monkeypatch=monkeypatch)

    async def _record_filters(*, session: AsyncSession) -> GlobalApiSyncResult:
        del session
        return GlobalApiSyncResult(
            processed=7,
            created=4,
            updated=3,
            errors=1,
            warnings=2,
        )

    monkeypatch.setattr(
        globalapi_sync,
        "GLOBALAPI_SYNC_TASKS",
        (globalapi_sync.GlobalApiSyncTask("record_filters", 86_400, _record_filters),),
    )

    await globalapi_sync.run_globalapi_sync_tasks(only_stale=False)

    state = await db.get(GlobalApiSyncState, "record_filters")
    assert state is not None
    assert state.last_processed == 7
    assert state.last_created == 4
    assert state.last_updated == 3
    assert state.last_errors == 1
    assert state.last_warnings == 2


async def test_run_globalapi_sync_tasks_runs_scheduled_record_filters_after_2am_utc(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_session_maker(db=db, monkeypatch=monkeypatch)
    calls = 0
    now = datetime(2026, 4, 4, 2, 5, tzinfo=UTC)
    await db.exec(
        delete(GlobalApiSyncState).where(
            GlobalApiSyncState.task_name == "record_filters"
        )
    )
    await db.commit()

    db.add(
        GlobalApiSyncState(
            task_name="record_filters",
            last_successful_at=datetime(2026, 4, 3, 2, 5, tzinfo=UTC),
        )
    )
    await db.commit()

    async def _record_filters(*, session: AsyncSession) -> GlobalApiSyncResult:
        nonlocal calls
        del session
        calls += 1
        return GlobalApiSyncResult(processed=1, created=1, updated=0, errors=0)

    monkeypatch.setattr(globalapi_sync, "get_datetime_utc", lambda: now)
    monkeypatch.setattr(
        globalapi_sync,
        "GLOBALAPI_SYNC_TASKS",
        (
            globalapi_sync.GlobalApiSyncTask(
                "record_filters",
                86_400,
                _record_filters,
                schedule_hour_utc=2,
                startup_stale_after_seconds=86_400,
            ),
        ),
    )

    await globalapi_sync.run_globalapi_sync_tasks(only_stale=True)
    assert calls == 1


async def test_run_globalapi_sync_tasks_skips_scheduled_record_filters_before_2am_utc(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_session_maker(db=db, monkeypatch=monkeypatch)
    calls = 0
    now = datetime(2026, 4, 4, 1, 30, tzinfo=UTC)
    await db.exec(
        delete(GlobalApiSyncState).where(
            GlobalApiSyncState.task_name == "record_filters"
        )
    )
    await db.commit()

    db.add(
        GlobalApiSyncState(
            task_name="record_filters",
            last_successful_at=datetime(2026, 4, 3, 2, 5, tzinfo=UTC),
        )
    )
    await db.commit()

    async def _record_filters(*, session: AsyncSession) -> GlobalApiSyncResult:
        nonlocal calls
        del session
        calls += 1
        return GlobalApiSyncResult(processed=1, created=1, updated=0, errors=0)

    monkeypatch.setattr(globalapi_sync, "get_datetime_utc", lambda: now)
    monkeypatch.setattr(
        globalapi_sync,
        "GLOBALAPI_SYNC_TASKS",
        (
            globalapi_sync.GlobalApiSyncTask(
                "record_filters",
                86_400,
                _record_filters,
                schedule_hour_utc=2,
                startup_stale_after_seconds=86_400,
            ),
        ),
    )

    await globalapi_sync.run_globalapi_sync_tasks(only_stale=True)
    assert calls == 0


async def test_run_globalapi_sync_tasks_runs_record_filters_on_startup_when_older_than_24h(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_session_maker(db=db, monkeypatch=monkeypatch)
    calls = 0
    now = datetime(2026, 4, 4, 1, 0, tzinfo=UTC)
    await db.exec(
        delete(GlobalApiSyncState).where(
            GlobalApiSyncState.task_name == "record_filters"
        )
    )
    await db.commit()

    db.add(
        GlobalApiSyncState(
            task_name="record_filters",
            last_successful_at=datetime(2026, 4, 2, 23, 59, tzinfo=UTC),
        )
    )
    await db.commit()

    async def _record_filters(*, session: AsyncSession) -> GlobalApiSyncResult:
        nonlocal calls
        del session
        calls += 1
        return GlobalApiSyncResult(processed=1, created=0, updated=1, errors=0)

    monkeypatch.setattr(globalapi_sync, "get_datetime_utc", lambda: now)
    monkeypatch.setattr(
        globalapi_sync,
        "GLOBALAPI_SYNC_TASKS",
        (
            globalapi_sync.GlobalApiSyncTask(
                "record_filters",
                86_400,
                _record_filters,
                schedule_hour_utc=2,
                startup_stale_after_seconds=86_400,
            ),
        ),
    )

    await globalapi_sync.run_globalapi_sync_tasks(only_stale=True, startup=True)
    assert calls == 1


async def test_run_globalapi_sync_tasks_skips_record_filters_on_startup_when_fresher_than_24h(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_session_maker(db=db, monkeypatch=monkeypatch)
    calls = 0
    now = datetime(2026, 4, 4, 1, 0, tzinfo=UTC)
    await db.exec(
        delete(GlobalApiSyncState).where(
            GlobalApiSyncState.task_name == "record_filters"
        )
    )
    await db.commit()

    db.add(
        GlobalApiSyncState(
            task_name="record_filters",
            last_successful_at=datetime(2026, 4, 3, 2, 5, tzinfo=UTC),
        )
    )
    await db.commit()

    async def _record_filters(*, session: AsyncSession) -> GlobalApiSyncResult:
        nonlocal calls
        del session
        calls += 1
        return GlobalApiSyncResult(processed=1, created=0, updated=1, errors=0)

    monkeypatch.setattr(globalapi_sync, "get_datetime_utc", lambda: now)
    monkeypatch.setattr(
        globalapi_sync,
        "GLOBALAPI_SYNC_TASKS",
        (
            globalapi_sync.GlobalApiSyncTask(
                "record_filters",
                86_400,
                _record_filters,
                schedule_hour_utc=2,
                startup_stale_after_seconds=86_400,
            ),
        ),
    )

    await globalapi_sync.run_globalapi_sync_tasks(only_stale=True, startup=True)
    assert calls == 0
