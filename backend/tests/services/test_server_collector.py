from __future__ import annotations

import asyncio
import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.crud import server as server_crud
from app.models import ServerStatus
from app.services import server_collector
from app.services.server_query import A2SInfoResult
from tests.utils.server import create_server

pytestmark = pytest.mark.asyncio


class _StaticSessionFactory:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def __call__(self) -> _StaticSessionContext:
        return _StaticSessionContext(self._session)


class _StaticSessionContext:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


@pytest.fixture(autouse=True)
def reset_collector_constants() -> Generator[None]:
    original_failures = server_collector.SERVER_A2S_FAILURES_BEFORE_OFFLINE
    original_poll = server_collector.SERVER_A2S_POLL_SECONDS
    yield
    server_collector.SERVER_A2S_FAILURES_BEFORE_OFFLINE = original_failures
    server_collector.SERVER_A2S_POLL_SECONDS = original_poll


def test_build_scheduler_ring_spreads_same_ip_targets() -> None:
    targets = [
        server_collector.CollectorTarget(
            server_id=uuid.uuid4(),
            ip="10.0.0.1",
            port=27015,
            stable_id="a-1",
        ),
        server_collector.CollectorTarget(
            server_id=uuid.uuid4(),
            ip="10.0.0.1",
            port=27016,
            stable_id="a-2",
        ),
        server_collector.CollectorTarget(
            server_id=uuid.uuid4(),
            ip="10.0.0.2",
            port=27015,
            stable_id="b-1",
        ),
        server_collector.CollectorTarget(
            server_id=uuid.uuid4(),
            ip="10.0.0.3",
            port=27015,
            stable_id="c-1",
        ),
    ]

    ring = server_collector.build_scheduler_ring(targets)

    assert [target.stable_id for target in ring] == ["a-1", "b-1", "a-2", "c-1"]


async def test_apply_query_outcome_success_updates_db_and_notifies(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = await create_server(db, hostname="Old Host", map_name="kz_old")
    notified_server_ids: list[uuid.UUID] = []

    monkeypatch.setattr(
        server_collector,
        "async_session_maker",
        _StaticSessionFactory(db),
    )

    async def _fake_notify(*, session: AsyncSession, server_id: uuid.UUID) -> None:
        del session
        notified_server_ids.append(server_id)

    monkeypatch.setattr(server_crud, "notify_server_status_updated", _fake_notify)

    await server_collector._apply_query_outcome(
        server_collector.CollectorQueryOutcome(
            server_id=server.id,
            success=True,
            info=A2SInfoResult(
                hostname="New Host",
                map_name="kz_new",
                player_count=2,
                max_players=16,
                players=[{"name": "Alice"}],
                observed_at=datetime.now(UTC),
                game_directory="csgo",
                game_name="Counter-Strike: Global Offensive",
                app_id=730,
            ),
            observed_at=datetime.now(UTC),
        )
    )

    refreshed = await crud.get_server_by_id(session=db, server_id=server.id)
    assert refreshed is not None
    assert refreshed.live_status is not None
    assert refreshed.live_status.hostname == "New Host"
    assert refreshed.live_status.map == "kz_new"
    assert notified_server_ids == [server.id]


async def test_apply_query_outcome_failure_keeps_online_until_threshold_then_offline(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = await create_server(db, player_count=4, max_players=20)
    assert server.live_status is not None
    previous_success_at = datetime.now(UTC) - timedelta(seconds=10)
    server.live_status.is_online = True
    server.live_status.players = [{"name": "Player One"}]
    server.live_status.state = {
        **server.live_status.state,
        "last_successful_seen_at": previous_success_at.isoformat(),
        "last_a2s_seen_at": previous_success_at.isoformat(),
        "timeout_count": 28,
    }
    db.add(server.live_status)
    await db.commit()

    monkeypatch.setattr(
        server_collector,
        "async_session_maker",
        _StaticSessionFactory(db),
    )
    monkeypatch.setattr(
        server_crud,
        "notify_server_status_updated",
        lambda **_: asyncio.sleep(0),
    )
    server_collector.SERVER_A2S_FAILURES_BEFORE_OFFLINE = 30

    await server_collector._apply_query_outcome(
        server_collector.CollectorQueryOutcome(
            server_id=server.id,
            success=False,
            info=None,
            observed_at=datetime.now(UTC),
        )
    )
    still_online = await crud.get_server_by_id(session=db, server_id=server.id)
    assert still_online is not None
    assert still_online.live_status is not None
    assert still_online.live_status.is_online is True
    assert still_online.live_status.state["timeout_count"] == 29

    await server_collector._apply_query_outcome(
        server_collector.CollectorQueryOutcome(
            server_id=server.id,
            success=False,
            info=None,
            observed_at=datetime.now(UTC),
        )
    )
    offline = await crud.get_server_by_id(session=db, server_id=server.id)
    assert offline is not None
    assert offline.status == ServerStatus.ENABLED
    assert offline.live_status is not None
    assert offline.live_status.is_online is False
    assert offline.live_status.player_count == 0
    assert offline.live_status.state["timeout_count"] == 30


async def test_run_server_query_collector_never_queries_same_server_concurrently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = server_collector.CollectorTarget(
        server_id=uuid.uuid4(),
        ip="127.0.0.1",
        port=27015,
        stable_id="server-1",
    )
    release = asyncio.Event()
    query_count = 0
    concurrent = 0
    max_concurrent = 0
    sleep_calls = 0

    async def _fake_load_targets(*, now: datetime) -> list[server_collector.CollectorTarget]:
        del now
        return [target]

    async def _fake_query(
        *,
        ip: str,
        port: int,
        timeout: float,
        players_timeout: float,
    ) -> A2SInfoResult:
        nonlocal query_count, concurrent, max_concurrent
        del ip, port, timeout, players_timeout
        query_count += 1
        concurrent += 1
        max_concurrent = max(max_concurrent, concurrent)
        try:
            await release.wait()
            return A2SInfoResult(
                hostname="Recovered Host",
                map_name="kz_recovered",
                player_count=0,
                max_players=16,
                players=[],
                observed_at=datetime.now(UTC),
            )
        finally:
            concurrent -= 1

    async def _fake_sleep(seconds: float) -> None:
        nonlocal sleep_calls
        del seconds
        sleep_calls += 1
        if sleep_calls == 3:
            release.set()
        if sleep_calls > 6:
            raise asyncio.CancelledError
        await asyncio.sleep(0)

    monkeypatch.setattr(server_collector, "_apply_query_outcome", lambda outcome: asyncio.sleep(0))

    with pytest.raises(asyncio.CancelledError):
        await server_collector.run_server_query_collector(
            query_fn=_fake_query,
            load_targets_fn=_fake_load_targets,
            sleep=_fake_sleep,
        )

    assert query_count >= 1
    assert max_concurrent == 1


async def test_wait_for_tick_deadline_applies_outcome_before_tick_expires(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = server_collector.CollectorTarget(
        server_id=uuid.uuid4(),
        ip="127.0.0.1",
        port=27015,
        stable_id="server-1",
    )
    observed_at = datetime.now(UTC)
    outcome = server_collector.CollectorQueryOutcome(
        server_id=target.server_id,
        success=True,
        info=A2SInfoResult(
            hostname="Immediate Host",
            map_name="kz_now",
            player_count=0,
            max_players=16,
            players=[],
            observed_at=observed_at,
        ),
        observed_at=observed_at,
    )
    completed_queue: asyncio.Queue[server_collector.CollectorQueryOutcome] = (
        asyncio.Queue()
    )
    pending_by_id = {target.server_id: target}
    applied: list[float] = []
    loop = asyncio.get_running_loop()

    async def _fake_apply_query_outcome(
        incoming: server_collector.CollectorQueryOutcome,
    ) -> None:
        assert incoming is outcome
        applied.append(loop.time())

    monkeypatch.setattr(
        server_collector,
        "_apply_query_outcome",
        _fake_apply_query_outcome,
    )

    async def _push_outcome() -> None:
        await asyncio.sleep(0.01)
        await completed_queue.put(outcome)

    start = loop.time()
    tick_deadline = start + 0.2
    push_task = asyncio.create_task(_push_outcome())
    await server_collector._wait_for_tick_deadline(
        tick_deadline=tick_deadline,
        completed_queue=completed_queue,
        pending_by_id=pending_by_id,
        sleep=asyncio.sleep,
    )
    await push_task

    assert applied
    assert applied[0] - start < 0.1
    assert target.server_id not in pending_by_id
