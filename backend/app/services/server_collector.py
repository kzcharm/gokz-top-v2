from __future__ import annotations

import asyncio
import uuid
from collections import defaultdict
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime

import psycopg

from app import crud
from app.core.config import settings
from app.core.db import async_session_maker
from app.models import ServerStatus
from app.services.server_events import broadcast_server_update
from app.services.server_query import (
    A2SInfoResult,
    ServerQueryError,
    query_server_a2s_info,
)

SERVER_PLUGIN_FRESH_SECONDS = 5
SERVER_A2S_POLL_SECONDS = 10
SERVER_A2S_INFO_TIMEOUT_SECONDS = 10.0
SERVER_A2S_PLAYERS_TIMEOUT_SECONDS = 10.0
SERVER_A2S_OFFLINE_SECONDS = 300
SERVER_A2S_FAILURES_BEFORE_OFFLINE = SERVER_A2S_OFFLINE_SECONDS // SERVER_A2S_POLL_SECONDS
SERVER_COLLECTOR_IDLE_SECONDS = 1.0
SERVER_STATUS_COLLECTOR_LOCK_ID = 4_465_480


@dataclass(slots=True, frozen=True)
class CollectorTarget:
    server_id: uuid.UUID
    ip: str
    port: int
    stable_id: str

    @property
    def endpoint(self) -> str:
        return f"{self.ip}:{self.port}"


@dataclass(slots=True, frozen=True)
class CollectorQueryOutcome:
    server_id: uuid.UUID
    success: bool
    info: A2SInfoResult | None
    observed_at: datetime


def build_scheduler_ring(targets: list[CollectorTarget]) -> list[CollectorTarget]:
    if not targets:
        return []

    by_host: dict[str, list[CollectorTarget]] = defaultdict(list)
    for target in targets:
        by_host[target.ip].append(target)

    same_ip_groups = [
        sorted(group, key=lambda item: item.stable_id)
        for group in by_host.values()
        if len(group) > 1
    ]
    same_ip_groups.sort(key=lambda group: group[0].stable_id)

    singletons = sorted(
        [group[0] for group in by_host.values() if len(group) == 1],
        key=lambda item: item.stable_id,
    )

    ring: list[CollectorTarget | None] = [None] * len(targets)
    for group in same_ip_groups:
        group_size = len(group)
        for index, target in enumerate(group):
            slot = int(index * len(targets) / group_size)
            while ring[slot] is not None:
                slot = (slot + 1) % len(targets)
            ring[slot] = target

    singleton_iter = iter(singletons)
    for index, slot_value in enumerate(ring):
        if slot_value is None:
            ring[index] = next(singleton_iter)

    filled_ring: list[CollectorTarget] = []
    for slot_value in ring:
        if slot_value is None:
            raise RuntimeError("Collector ring contains an empty slot")
        filled_ring.append(slot_value)
    return filled_ring


def compute_tick_spacing(*, interval_seconds: float, ring_size: int) -> float:
    if ring_size <= 0:
        raise ValueError("ring_size must be greater than zero")
    return interval_seconds / ring_size


def _resume_cursor_index(
    *,
    ring: list[CollectorTarget],
    last_stable_id: str | None,
) -> int:
    if last_stable_id is None:
        return 0
    for index, target in enumerate(ring):
        if target.stable_id == last_stable_id:
            return (index + 1) % len(ring)
    return 0


async def _default_sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


def _psycopg_database_uri() -> str:
    return str(settings.SQLALCHEMY_DATABASE_URI).replace(
        "postgresql+psycopg", "postgresql", 1
    )


async def load_due_targets(*, now: datetime) -> list[CollectorTarget]:
    async with async_session_maker() as session:
        servers = await crud.read_servers_due_for_a2s_poll(
            session=session,
            now=now,
            plugin_stale_after_seconds=SERVER_PLUGIN_FRESH_SECONDS,
            a2s_poll_after_seconds=SERVER_A2S_POLL_SECONDS,
        )
    return [
        CollectorTarget(
            server_id=server.id,
            ip=server.ip,
            port=server.port,
            stable_id=str(server.id),
        )
        for server in servers
    ]


async def _run_probe(
    *,
    target: CollectorTarget,
    query_fn: Callable[..., Awaitable[A2SInfoResult]],
) -> CollectorQueryOutcome:
    try:
        info = await query_fn(
            ip=target.ip,
            port=target.port,
            timeout=SERVER_A2S_INFO_TIMEOUT_SECONDS,
            players_timeout=SERVER_A2S_PLAYERS_TIMEOUT_SECONDS,
        )
    except ServerQueryError:
        return CollectorQueryOutcome(
            server_id=target.server_id,
            success=False,
            info=None,
            observed_at=datetime.now(UTC),
        )
    return CollectorQueryOutcome(
        server_id=target.server_id,
        success=True,
        info=info,
        observed_at=info.observed_at,
    )


async def _apply_query_outcome(outcome: CollectorQueryOutcome) -> None:
    async with async_session_maker() as session:
        server = await crud.get_server_by_id(session=session, server_id=outcome.server_id)
        if server is None or server.status == ServerStatus.DISABLED:
            return

        before_public = crud.to_server_public(server=server).model_dump(mode="json")
        if outcome.success:
            assert outcome.info is not None
            updated = await crud.record_a2s_success(
                session=session,
                server=server,
                observed_at=outcome.info.observed_at,
                hostname=outcome.info.hostname,
                map_name=outcome.info.map_name,
                player_count=outcome.info.player_count,
                max_players=outcome.info.max_players,
                players=outcome.info.players,
                notify=False,
            )
        else:
            updated = await crud.record_a2s_failure(
                session=session,
                server=server,
                observed_at=outcome.observed_at,
                offline_after_failures=SERVER_A2S_FAILURES_BEFORE_OFFLINE,
                notify=False,
            )

    after_public = crud.to_server_public(server=updated).model_dump(mode="json")
    if before_public != after_public:
        await broadcast_server_update(updated)


def _drain_completed_outcomes(
    *,
    completed_queue: asyncio.Queue[CollectorQueryOutcome],
    pending_by_id: dict[uuid.UUID, CollectorTarget],
) -> list[CollectorQueryOutcome]:
    outcomes: list[CollectorQueryOutcome] = []
    while True:
        try:
            outcome = completed_queue.get_nowait()
        except asyncio.QueueEmpty:
            break
        pending_by_id.pop(outcome.server_id, None)
        outcomes.append(outcome)
    return outcomes


async def _wait_for_tick_deadline(
    *,
    tick_deadline: float,
    completed_queue: asyncio.Queue[CollectorQueryOutcome],
    pending_by_id: dict[uuid.UUID, CollectorTarget],
    sleep: Callable[[float], Awaitable[None]],
) -> None:
    loop = asyncio.get_running_loop()

    while True:
        for outcome in _drain_completed_outcomes(
            completed_queue=completed_queue,
            pending_by_id=pending_by_id,
        ):
            await _apply_query_outcome(outcome)

        remaining = tick_deadline - loop.time()
        if remaining <= 0:
            return

        sleep_task = asyncio.create_task(sleep(remaining))
        outcome_task = asyncio.create_task(completed_queue.get())
        done, pending = await asyncio.wait(
            {sleep_task, outcome_task},
            return_when=asyncio.FIRST_COMPLETED,
        )

        if outcome_task in done:
            sleep_task.cancel()
            with suppress(asyncio.CancelledError):
                await sleep_task
            outcome = outcome_task.result()
            pending_by_id.pop(outcome.server_id, None)
            await _apply_query_outcome(outcome)
            continue

        outcome_task.cancel()
        with suppress(asyncio.CancelledError):
            await outcome_task

        for task in pending:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        await sleep_task
        return


async def run_server_query_collector(
    *,
    query_fn: Callable[..., Awaitable[A2SInfoResult]] = query_server_a2s_info,
    load_targets_fn: Callable[..., Awaitable[list[CollectorTarget]]] = load_due_targets,
    sleep: Callable[[float], Awaitable[None]] = _default_sleep,
) -> None:
    pending_by_id: dict[uuid.UUID, CollectorTarget] = {}
    live_tasks: set[asyncio.Task[CollectorQueryOutcome]] = set()
    completed_queue: asyncio.Queue[CollectorQueryOutcome] = asyncio.Queue()
    last_stable_id: str | None = None

    def _on_task_done(task: asyncio.Task[CollectorQueryOutcome]) -> None:
        live_tasks.discard(task)
        with suppress(asyncio.CancelledError):
            completed_queue.put_nowait(task.result())

    try:
        while True:
            for outcome in _drain_completed_outcomes(
                completed_queue=completed_queue,
                pending_by_id=pending_by_id,
            ):
                await _apply_query_outcome(outcome)
            targets = await load_targets_fn(now=datetime.now(UTC))
            ring = build_scheduler_ring(targets)
            if not ring:
                await sleep(SERVER_COLLECTOR_IDLE_SECONDS)
                continue

            tick_spacing = compute_tick_spacing(
                interval_seconds=SERVER_A2S_POLL_SECONDS,
                ring_size=len(ring),
            )
            cursor_index = _resume_cursor_index(ring=ring, last_stable_id=last_stable_id)

            for _ in range(len(ring)):
                target = ring[cursor_index]
                last_stable_id = target.stable_id
                if target.server_id not in pending_by_id:
                    pending_by_id[target.server_id] = target
                    task = asyncio.create_task(_run_probe(target=target, query_fn=query_fn))
                    live_tasks.add(task)
                    task.add_done_callback(_on_task_done)

                tick_deadline = asyncio.get_running_loop().time() + tick_spacing
                await _wait_for_tick_deadline(
                    tick_deadline=tick_deadline,
                    completed_queue=completed_queue,
                    pending_by_id=pending_by_id,
                    sleep=sleep,
                )
                cursor_index = (cursor_index + 1) % len(ring)
    finally:
        for task in live_tasks:
            task.cancel()
        for task in list(live_tasks):
            with suppress(asyncio.CancelledError):
                await task


async def run_server_query_collector_in_app() -> None:
    while True:
        try:
            async with await psycopg.AsyncConnection.connect(
                _psycopg_database_uri(),
                autocommit=True,
            ) as connection:
                async with connection.cursor() as cursor:
                    await cursor.execute(
                        "SELECT pg_try_advisory_lock(%s)",
                        (SERVER_STATUS_COLLECTOR_LOCK_ID,),
                    )
                    row = await cursor.fetchone()
                if not row or row[0] is not True:
                    await asyncio.sleep(5)
                    continue

                try:
                    await run_server_query_collector()
                finally:
                    with suppress(Exception):
                        async with connection.cursor() as cursor:
                            await cursor.execute(
                                "SELECT pg_advisory_unlock(%s)",
                                (SERVER_STATUS_COLLECTOR_LOCK_ID,),
                            )
        except asyncio.CancelledError:
            raise
        except Exception:
            await asyncio.sleep(1)


async def stop_collector(task: asyncio.Task[None] | None) -> None:
    if task is None:
        return
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
