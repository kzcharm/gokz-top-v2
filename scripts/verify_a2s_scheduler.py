#!/usr/bin/env python3
"""Verify a cursor-scheduled A2S query strategy against the live public fleet.

This script is intentionally standalone and diagnostic-only. It does not import
application modules, does not write to the database, and does not try to be the
final production collector. Its job is narrower: validate whether a paced,
cursor-based scheduler improves real-world A2S success rates compared with the
earlier "launch everything at once" benchmark.

The key design constraint is that the code should read like a reference
implementation for future business logic. The larger comment blocks below are
there on purpose so the eventual production port can preserve the scheduling
semantics without re-deriving them from scratch.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import httpx
from a2s.a2s_async import (  # type: ignore[import-untyped]
    A2SStreamAsync,
    request_async_impl,
)
from a2s.info import InfoProtocol  # type: ignore[import-untyped]
from a2s.players import PlayersProtocol  # type: ignore[import-untyped]
from rich.console import Console
from rich.table import Table

DEFAULT_API_URL = "https://api.gokz.top/api/v1/public-servers/status/?offset=0&limit=100"
DEFAULT_DURATION_SECONDS = 300
DEFAULT_INTERVAL_SECONDS = 10.0
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_SUMMARY_INTERVAL_SECONDS = 5.0
DEFAULT_OFFENDER_LIMIT = 10


class QueryServerA2SFn(Protocol):
    async def __call__(
        self,
        *,
        ip: str,
        port: int,
        timeout: float,
        players_timeout: float,
    ) -> ProbeQueryResult: ...


class FetchTargetsFn(Protocol):
    async def __call__(self, api_url: str) -> list[SchedulerTarget]: ...


type SleepFn = Callable[[float], Awaitable[None]]
type ProgressMessageFn = Callable[[str], None]


@dataclass(slots=True, frozen=True)
class SchedulerTarget:
    host: str
    port: int
    hostname: str | None
    country: str | None
    group_name: str | None
    group_custom_id: str | None
    server_id: str | None
    stable_id: str

    @property
    def endpoint(self) -> str:
        return f"{self.host}:{self.port}"

    @property
    def display_name(self) -> str:
        return self.hostname or self.endpoint


@dataclass(slots=True, frozen=True)
class ProbeQueryResult:
    map_name: str | None
    player_count: int | None
    info_elapsed_ms: float
    players_elapsed_ms: float | None
    players_queried: bool
    players_returned: int | None


@dataclass(slots=True)
class ProbeQueryError(RuntimeError):
    stage: str
    timed_out: bool
    info_elapsed_ms: float | None = None
    players_elapsed_ms: float | None = None

    def __post_init__(self) -> None:
        super().__init__(self.stage)


@dataclass(slots=True, frozen=True)
class PendingState:
    stable_id: str
    endpoint: str
    slot_index: int
    launched_at: datetime
    launched_monotonic: float


@dataclass(slots=True, frozen=True)
class ProbeAttempt:
    stable_id: str
    host: str
    port: int
    endpoint: str
    hostname: str | None
    country: str | None
    group_name: str | None
    slot_index: int
    started_at: datetime
    completed_at: datetime
    elapsed_ms: float
    info_elapsed_ms: float | None
    players_elapsed_ms: float | None
    players_queried: bool
    players_returned: int | None
    success: bool
    timed_out: bool
    failure_stage: str | None
    error: str | None


@dataclass(slots=True, frozen=True)
class ServerAggregate:
    target: SchedulerTarget
    attempts: int
    successes: int
    timeouts: int
    other_failures: int
    info_timeouts: int
    players_timeouts: int
    pending_skips: int
    timeout_rate: float
    avg_latency_ms: float | None
    max_latency_ms: float | None


@dataclass(slots=True, frozen=True)
class HostAggregate:
    host: str
    endpoints: list[str]
    attempts: int
    successes: int
    timeouts: int
    other_failures: int
    info_timeouts: int
    players_timeouts: int
    pending_skips: int
    timeout_rate: float
    avg_latency_ms: float | None
    max_latency_ms: float | None


@dataclass(slots=True, frozen=True)
class SchedulerSummary:
    api_url: str
    configured_duration_seconds: int
    interval_seconds: float
    info_timeout_seconds: float
    players_timeout_seconds: float
    started_at: datetime
    completed_at: datetime
    target_count: int
    tick_spacing_seconds: float
    total_launches: int
    successful_attempts: int
    timeout_attempts: int
    other_failures: int
    info_timeout_attempts: int
    players_timeout_attempts: int
    pending_skip_count: int
    avg_latency_ms: float | None
    max_latency_ms: float | None
    ring: list[SchedulerTarget]
    attempts: list[ProbeAttempt]
    pending_skip_counts: dict[str, int]
    per_server: list[ServerAggregate]
    per_host: list[HostAggregate]


class _ClosedTransport:
    def close(self) -> None:
        return


def _ensure_int(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"Expected {field_name} to be an integer")
    return int(value)


def parse_public_server_payload(payload: dict[str, Any]) -> list[SchedulerTarget]:
    rows = payload.get("data")
    if not isinstance(rows, list):
        raise ValueError("Expected API payload to include a list in 'data'")

    deduped_targets: list[SchedulerTarget] = []
    seen_endpoints: set[tuple[str, int]] = set()

    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("is_online") is not True:
            continue

        host = row.get("host")
        port = row.get("port")
        if not isinstance(host, str) or not host.strip():
            continue
        try:
            normalized_port = _ensure_int(port, field_name="port")
        except ValueError:
            continue
        endpoint = (host.strip(), normalized_port)
        if endpoint in seen_endpoints:
            continue
        seen_endpoints.add(endpoint)

        server_id = row.get("server_id") if isinstance(row.get("server_id"), str) else None
        stable_id = server_id or f"{endpoint[0]}:{endpoint[1]}"
        deduped_targets.append(
            SchedulerTarget(
                host=endpoint[0],
                port=endpoint[1],
                hostname=row.get("hostname") if isinstance(row.get("hostname"), str) else None,
                country=row.get("country") if isinstance(row.get("country"), str) else None,
                group_name=row.get("group_name")
                if isinstance(row.get("group_name"), str)
                else None,
                group_custom_id=row.get("group_custom_id")
                if isinstance(row.get("group_custom_id"), str)
                else None,
                server_id=server_id,
                stable_id=stable_id,
            )
        )

    return deduped_targets


async def fetch_online_targets(api_url: str) -> list[SchedulerTarget]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(api_url)
        response.raise_for_status()
        payload = response.json()

    if not isinstance(payload, dict):
        raise ValueError("Expected public server API to return a JSON object")

    targets = parse_public_server_payload(payload)
    if not targets:
        raise ValueError("No online servers were returned by the public server API")
    return targets


async def request_a2s_protocol(
    *,
    address: tuple[str, int],
    timeout: float,
    encoding: str,
    protocol: type[Any],
) -> Any:
    """Run one low-level python-a2s request and always close its UDP transport.

    python-a2s exposes convenient high-level async helpers, but those helpers
    only close the underlying datagram transport on the success path. For a test
    that intentionally expects many timeouts and failures, that behavior leaks
    transports until garbage collection and then emits "event loop is closed"
    noise during object destruction.

    The production implementation should keep this invariant too: every request
    attempt owns exactly one transport, and that transport must be closed in a
    finally block no matter how the request ends.
    """

    conn = await A2SStreamAsync.create(address, timeout)
    try:
        return await request_async_impl(conn, encoding, protocol)
    finally:
        transport = getattr(conn, "transport", None)
        conn.transport = _ClosedTransport()
        if transport is not None:
            transport.close()


async def query_server_a2s(
    *,
    ip: str,
    port: int,
    timeout: float,
    players_timeout: float,
) -> ProbeQueryResult:
    address = (ip, port)
    info_started = time.perf_counter()
    try:
        info = await request_a2s_protocol(
            address=address,
            timeout=timeout,
            encoding="utf-8",
            protocol=InfoProtocol,
        )
    except Exception as exc:
        info_elapsed_ms = (time.perf_counter() - info_started) * 1000
        raise ProbeQueryError(
            stage="info",
            timed_out=is_timeout_error(exc),
            info_elapsed_ms=round(info_elapsed_ms, 3),
        ) from exc

    info_elapsed_ms = (time.perf_counter() - info_started) * 1000
    player_count = int(info.player_count)
    map_name = str(info.map_name)
    if player_count <= 0:
        return ProbeQueryResult(
            map_name=map_name,
            player_count=player_count,
            info_elapsed_ms=round(info_elapsed_ms, 3),
            players_elapsed_ms=None,
            players_queried=False,
            players_returned=None,
        )

    players_started = time.perf_counter()
    try:
        players = await request_a2s_protocol(
            address=address,
            timeout=players_timeout,
            encoding="utf-8",
            protocol=PlayersProtocol,
        )
    except Exception as exc:
        players_elapsed_ms = (time.perf_counter() - players_started) * 1000
        raise ProbeQueryError(
            stage="players",
            timed_out=is_timeout_error(exc),
            info_elapsed_ms=round(info_elapsed_ms, 3),
            players_elapsed_ms=round(players_elapsed_ms, 3),
        ) from exc

    players_elapsed_ms = (time.perf_counter() - players_started) * 1000
    return ProbeQueryResult(
        map_name=map_name,
        player_count=player_count,
        info_elapsed_ms=round(info_elapsed_ms, 3),
        players_elapsed_ms=round(players_elapsed_ms, 3),
        players_queried=True,
        players_returned=len(players),
    )


def is_timeout_error(exc: BaseException) -> bool:
    current: BaseException | None = exc
    seen_ids: set[int] = set()
    while current is not None and id(current) not in seen_ids:
        if isinstance(current, TimeoutError):
            return True
        message = str(current).casefold()
        if "timed out" in message or message == "timeout":
            return True
        seen_ids.add(id(current))
        current = current.__cause__ or current.__context__
    return False


def spread_same_ip_groups(
    groups: list[list[SchedulerTarget]],
    ring_size: int,
) -> list[SchedulerTarget | None]:
    """Place same-IP server groups into a ring before singletons are filled.

    This helper is the heart of the placement strategy. Servers that share a
    host are the ones most likely to interfere with each other if queried back
    to back, so they get first claim on ring positions. Each group is sorted by
    stable id and then assigned "ideal" positions that are evenly spaced across
    the full ring length. When a slot is already occupied, we walk forward
    circularly until we find the next empty position.

    The result is not mathematically optimal packing; it is deliberately simple,
    deterministic, and stable under small fleet changes. That stability matters
    more for later production use than squeezing out the last possible spacing
    improvement from one static snapshot.
    """

    ring: list[SchedulerTarget | None] = [None] * ring_size
    for group in groups:
        group_size = len(group)
        for index, target in enumerate(group):
            ideal_slot = int(index * ring_size / group_size)
            slot = ideal_slot
            while ring[slot] is not None:
                slot = (slot + 1) % ring_size
            ring[slot] = target
    return ring


def build_scheduler_ring(targets: list[SchedulerTarget]) -> list[SchedulerTarget]:
    """Build the deterministic cursor ring for one static fleet snapshot.

    Invariants:
    - multi-server hosts are intentionally spread throughout the ring first
    - placement is driven entirely by stable ids, so repeated runs with the same
      snapshot produce the same order
    - single-host endpoints do not compete with multi-host spreading; they only
      fill the gaps that remain

    This mirrors the intended production model where the ring is a scheduling
    primitive, not just a pretty ordering. The cursor will advance through this
    list at a steady cadence, so adjacency in the ring directly affects launch
    adjacency at runtime.
    """

    if not targets:
        return []

    by_host: dict[str, list[SchedulerTarget]] = defaultdict(list)
    for target in targets:
        by_host[target.host].append(target)

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

    ring = spread_same_ip_groups(same_ip_groups, len(targets))
    singleton_iter = iter(singletons)
    for index, slot_value in enumerate(ring):
        if slot_value is None:
            ring[index] = next(singleton_iter)
    filled_ring: list[SchedulerTarget] = []
    for slot_value in ring:
        if slot_value is None:
            raise RuntimeError("Scheduler ring still contains an empty slot")
        filled_ring.append(slot_value)
    return filled_ring


def compute_tick_spacing(interval_seconds: float, ring_size: int) -> float:
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be greater than zero")
    if ring_size <= 0:
        raise ValueError("ring_size must be greater than zero")
    return interval_seconds / ring_size


async def _default_sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


def _format_latency(value_ms: float | None) -> str:
    if value_ms is None:
        return "n/a"
    return f"{value_ms:.1f} ms"


def _format_rate(value: float) -> str:
    return f"{value * 100:.2f}%"


def _format_attempt_status(attempt: ProbeAttempt) -> str:
    if attempt.success:
        return f"{attempt.endpoint} ok in {attempt.elapsed_ms:.1f} ms"
    if attempt.timed_out:
        stage = attempt.failure_stage or "unknown"
        return f"{attempt.endpoint} {stage} timeout in {attempt.elapsed_ms:.1f} ms"
    return f"{attempt.endpoint} failed in {attempt.elapsed_ms:.1f} ms"


async def run_scheduler_benchmark(
    *,
    api_url: str,
    targets: list[SchedulerTarget],
    duration_seconds: int,
    interval_seconds: float,
    timeout_seconds: float,
    players_timeout_seconds: float,
    query_fn: QueryServerA2SFn,
    sleep: SleepFn = _default_sleep,
    monotonic: Callable[[], float] = time.monotonic,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    progress_message: ProgressMessageFn | None = None,
    summary_interval_seconds: float = DEFAULT_SUMMARY_INTERVAL_SECONDS,
) -> SchedulerSummary:
    if duration_seconds <= 0:
        raise ValueError("duration_seconds must be greater than zero")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be greater than zero")
    if players_timeout_seconds <= 0:
        raise ValueError("players_timeout_seconds must be greater than zero")

    ring = build_scheduler_ring(targets)
    if not ring:
        raise ValueError("At least one scheduler target is required")

    tick_spacing_seconds = compute_tick_spacing(interval_seconds, len(ring))
    started_at = now()
    launch_phase_deadline = monotonic() + duration_seconds
    next_tick_at = monotonic()
    next_summary_at = monotonic() + summary_interval_seconds
    cursor_index = 0
    attempts: list[ProbeAttempt] = []
    pending_by_id: dict[str, PendingState] = {}
    pending_skip_counts: dict[str, int] = defaultdict(int)
    completed_queue: asyncio.Queue[ProbeAttempt] = asyncio.Queue()
    live_tasks: set[asyncio.Task[ProbeAttempt]] = set()

    async def _probe_target(target: SchedulerTarget, slot_index: int) -> ProbeAttempt:
        started_at_inner = now()
        started_monotonic = monotonic()
        try:
            result = await query_fn(
                ip=target.host,
                port=target.port,
                timeout=timeout_seconds,
                players_timeout=players_timeout_seconds,
            )
        except ProbeQueryError as exc:
            completed_at_inner = now()
            elapsed_ms = (monotonic() - started_monotonic) * 1000
            cause = exc.__cause__
            error_message = (
                str(cause).strip()
                if cause is not None and str(cause).strip()
                else exc.__class__.__name__
            )
            return ProbeAttempt(
                stable_id=target.stable_id,
                host=target.host,
                port=target.port,
                endpoint=target.endpoint,
                hostname=target.hostname,
                country=target.country,
                group_name=target.group_name,
                slot_index=slot_index,
                started_at=started_at_inner,
                completed_at=completed_at_inner,
                elapsed_ms=round(elapsed_ms, 3),
                info_elapsed_ms=exc.info_elapsed_ms,
                players_elapsed_ms=exc.players_elapsed_ms,
                players_queried=exc.stage == "players",
                players_returned=None,
                success=False,
                timed_out=exc.timed_out,
                failure_stage=exc.stage,
                error=error_message,
            )
        except Exception as exc:
            completed_at_inner = now()
            elapsed_ms = (monotonic() - started_monotonic) * 1000
            return ProbeAttempt(
                stable_id=target.stable_id,
                host=target.host,
                port=target.port,
                endpoint=target.endpoint,
                hostname=target.hostname,
                country=target.country,
                group_name=target.group_name,
                slot_index=slot_index,
                started_at=started_at_inner,
                completed_at=completed_at_inner,
                elapsed_ms=round(elapsed_ms, 3),
                info_elapsed_ms=None,
                players_elapsed_ms=None,
                players_queried=False,
                players_returned=None,
                success=False,
                timed_out=is_timeout_error(exc),
                failure_stage=None,
                error=str(exc).strip() or exc.__class__.__name__,
            )

        completed_at_inner = now()
        elapsed_ms = (monotonic() - started_monotonic) * 1000
        return ProbeAttempt(
            stable_id=target.stable_id,
            host=target.host,
            port=target.port,
            endpoint=target.endpoint,
            hostname=target.hostname,
            country=target.country,
            group_name=target.group_name,
            slot_index=slot_index,
            started_at=started_at_inner,
            completed_at=completed_at_inner,
            elapsed_ms=round(elapsed_ms, 3),
            info_elapsed_ms=result.info_elapsed_ms,
            players_elapsed_ms=result.players_elapsed_ms,
            players_queried=result.players_queried,
            players_returned=result.players_returned,
            success=True,
            timed_out=False,
            failure_stage=None,
            error=None,
        )

    def _on_task_done(task: asyncio.Task[ProbeAttempt]) -> None:
        live_tasks.discard(task)
        with suppress(asyncio.CancelledError):
            completed_queue.put_nowait(task.result())

    # The scheduler loop is intentionally simple:
    # 1. advance a single cursor through the ring at a fixed cadence
    # 2. launch at most one new query per tick
    # 3. refuse to relaunch a server while its prior request is still pending
    #
    # This is the behavior we actually want to validate under live network
    # conditions. The ring defines pacing. Pending state defines "one in flight
    # per server". There are no batch objects hidden under the hood.
    while monotonic() < launch_phase_deadline:
        drain_completed_attempts(
            completed_queue=completed_queue,
            attempts=attempts,
            pending_by_id=pending_by_id,
            progress_message=progress_message,
        )
        sleep_seconds = next_tick_at - monotonic()
        if sleep_seconds > 0:
            await sleep(sleep_seconds)
            drain_completed_attempts(
                completed_queue=completed_queue,
                attempts=attempts,
                pending_by_id=pending_by_id,
                progress_message=progress_message,
            )

        target = ring[cursor_index]
        if target.stable_id in pending_by_id:
            pending_skip_counts[target.stable_id] += 1
            if progress_message is not None:
                progress_message(
                    " | ".join(
                        [
                            "Cursor skip",
                            f"slot {cursor_index + 1}/{len(ring)}",
                            target.endpoint,
                            "reason pending",
                            f"pending {len(pending_by_id)}",
                        ]
                    )
                )
        else:
            pending_by_id[target.stable_id] = PendingState(
                stable_id=target.stable_id,
                endpoint=target.endpoint,
                slot_index=cursor_index,
                launched_at=now(),
                launched_monotonic=monotonic(),
            )
            task = asyncio.create_task(_probe_target(target, cursor_index))
            live_tasks.add(task)
            task.add_done_callback(_on_task_done)
            if progress_message is not None:
                progress_message(
                    " | ".join(
                        [
                            "Cursor launch",
                            f"slot {cursor_index + 1}/{len(ring)}",
                            target.endpoint,
                            f"pending {len(pending_by_id)}",
                        ]
                    )
                )

        cursor_index = (cursor_index + 1) % len(ring)
        next_tick_at += tick_spacing_seconds

        if progress_message is not None and monotonic() >= next_summary_at:
            progress_message(
                " | ".join(
                    [
                        "Scheduler summary",
                        f"launches {len(attempts) + len(pending_by_id)}",
                        f"completed {len(attempts)}",
                        f"pending {len(pending_by_id)}",
                        f"pending skips {sum(pending_skip_counts.values())}",
                    ]
                )
            )
            next_summary_at += summary_interval_seconds

    if progress_message is not None:
        progress_message(
            " | ".join(
                [
                    "Launch phase finished",
                    f"in-flight {len(pending_by_id)}",
                    "waiting for pending queries to settle",
                ]
            )
        )

    while live_tasks or pending_by_id:
        if live_tasks:
            done, _ = await asyncio.wait(
                live_tasks,
                timeout=summary_interval_seconds,
                return_when=asyncio.FIRST_COMPLETED,
            )
            del done
        drain_completed_attempts(
            completed_queue=completed_queue,
            attempts=attempts,
            pending_by_id=pending_by_id,
            progress_message=progress_message,
        )
        if progress_message is not None and (live_tasks or pending_by_id):
            progress_message(
                " | ".join(
                    [
                        "Draining pending",
                        f"completed {len(attempts)}",
                        f"in-flight {len(live_tasks)}",
                        f"pending {len(pending_by_id)}",
                    ]
                )
            )

    completed_at = now()
    return build_scheduler_summary(
        api_url=api_url,
        configured_duration_seconds=duration_seconds,
        interval_seconds=interval_seconds,
        info_timeout_seconds=timeout_seconds,
        players_timeout_seconds=players_timeout_seconds,
        started_at=started_at,
        completed_at=completed_at,
        ring=ring,
        attempts=attempts,
        pending_skip_counts=dict(pending_skip_counts),
    )


def drain_completed_attempts(
    *,
    completed_queue: asyncio.Queue[ProbeAttempt],
    attempts: list[ProbeAttempt],
    pending_by_id: dict[str, PendingState],
    progress_message: ProgressMessageFn | None,
) -> None:
    while True:
        try:
            attempt = completed_queue.get_nowait()
        except asyncio.QueueEmpty:
            return
        attempts.append(attempt)
        pending_by_id.pop(attempt.stable_id, None)
        if progress_message is not None:
            progress_message(
                " | ".join(
                    [
                        "Completion",
                        _format_attempt_status(attempt),
                        f"pending {len(pending_by_id)}",
                    ]
                )
            )


def build_scheduler_summary(
    *,
    api_url: str,
    configured_duration_seconds: int,
    interval_seconds: float,
    info_timeout_seconds: float,
    players_timeout_seconds: float,
    started_at: datetime,
    completed_at: datetime,
    ring: list[SchedulerTarget],
    attempts: list[ProbeAttempt],
    pending_skip_counts: dict[str, int],
) -> SchedulerSummary:
    latency_samples_ms = [attempt.elapsed_ms for attempt in attempts if attempt.success]
    successful_attempts = sum(1 for attempt in attempts if attempt.success)
    timeout_attempts = sum(1 for attempt in attempts if attempt.timed_out)
    other_failures = sum(
        1 for attempt in attempts if not attempt.success and not attempt.timed_out
    )
    info_timeout_attempts = sum(
        1 for attempt in attempts if attempt.failure_stage == "info" and attempt.timed_out
    )
    players_timeout_attempts = sum(
        1
        for attempt in attempts
        if attempt.failure_stage == "players" and attempt.timed_out
    )

    by_stable_id = {target.stable_id: target for target in ring}
    attempts_by_server: dict[str, list[ProbeAttempt]] = defaultdict(list)
    attempts_by_host: dict[str, list[ProbeAttempt]] = defaultdict(list)
    for attempt in attempts:
        attempts_by_server[attempt.stable_id].append(attempt)
        attempts_by_host[attempt.host].append(attempt)

    per_server: list[ServerAggregate] = []
    for stable_id, target in by_stable_id.items():
        server_attempts = attempts_by_server.get(stable_id, [])
        successes = [attempt.elapsed_ms for attempt in server_attempts if attempt.success]
        timeouts = sum(1 for attempt in server_attempts if attempt.timed_out)
        other_server_failures = sum(
            1
            for attempt in server_attempts
            if not attempt.success and not attempt.timed_out
        )
        info_timeouts = sum(
            1
            for attempt in server_attempts
            if attempt.failure_stage == "info" and attempt.timed_out
        )
        players_timeouts = sum(
            1
            for attempt in server_attempts
            if attempt.failure_stage == "players" and attempt.timed_out
        )
        attempts_count = len(server_attempts)
        per_server.append(
            ServerAggregate(
                target=target,
                attempts=attempts_count,
                successes=len(successes),
                timeouts=timeouts,
                other_failures=other_server_failures,
                info_timeouts=info_timeouts,
                players_timeouts=players_timeouts,
                pending_skips=pending_skip_counts.get(stable_id, 0),
                timeout_rate=(timeouts / attempts_count) if attempts_count else 0.0,
                avg_latency_ms=(
                    round(sum(successes) / len(successes), 3) if successes else None
                ),
                max_latency_ms=(round(max(successes), 3) if successes else None),
            )
        )

    per_server.sort(
        key=lambda aggregate: (
            -aggregate.timeout_rate,
            -aggregate.timeouts,
            aggregate.target.endpoint,
        )
    )

    ring_hosts = {target.host for target in ring}
    endpoints_by_host: dict[str, list[str]] = defaultdict(list)
    pending_skips_by_host: dict[str, int] = defaultdict(int)
    for target in ring:
        endpoints_by_host[target.host].append(target.endpoint)
        pending_skips_by_host[target.host] += pending_skip_counts.get(target.stable_id, 0)

    per_host: list[HostAggregate] = []
    for host in sorted(ring_hosts):
        host_attempts = attempts_by_host.get(host, [])
        successes = [attempt.elapsed_ms for attempt in host_attempts if attempt.success]
        timeouts = sum(1 for attempt in host_attempts if attempt.timed_out)
        other_host_failures = sum(
            1 for attempt in host_attempts if not attempt.success and not attempt.timed_out
        )
        info_timeouts = sum(
            1
            for attempt in host_attempts
            if attempt.failure_stage == "info" and attempt.timed_out
        )
        players_timeouts = sum(
            1
            for attempt in host_attempts
            if attempt.failure_stage == "players" and attempt.timed_out
        )
        attempts_count = len(host_attempts)
        per_host.append(
            HostAggregate(
                host=host,
                endpoints=sorted(endpoints_by_host[host]),
                attempts=attempts_count,
                successes=len(successes),
                timeouts=timeouts,
                other_failures=other_host_failures,
                info_timeouts=info_timeouts,
                players_timeouts=players_timeouts,
                pending_skips=pending_skips_by_host[host],
                timeout_rate=(timeouts / attempts_count) if attempts_count else 0.0,
                avg_latency_ms=(
                    round(sum(successes) / len(successes), 3) if successes else None
                ),
                max_latency_ms=(round(max(successes), 3) if successes else None),
            )
        )

    per_host.sort(key=lambda aggregate: (-aggregate.timeout_rate, -aggregate.timeouts, aggregate.host))

    return SchedulerSummary(
        api_url=api_url,
        configured_duration_seconds=configured_duration_seconds,
        interval_seconds=interval_seconds,
        info_timeout_seconds=info_timeout_seconds,
        players_timeout_seconds=players_timeout_seconds,
        started_at=started_at,
        completed_at=completed_at,
        target_count=len(ring),
        tick_spacing_seconds=compute_tick_spacing(interval_seconds, len(ring)),
        total_launches=len(attempts),
        successful_attempts=successful_attempts,
        timeout_attempts=timeout_attempts,
        other_failures=other_failures,
        info_timeout_attempts=info_timeout_attempts,
        players_timeout_attempts=players_timeout_attempts,
        pending_skip_count=sum(pending_skip_counts.values()),
        avg_latency_ms=(
            round(sum(latency_samples_ms) / len(latency_samples_ms), 3)
            if latency_samples_ms
            else None
        ),
        max_latency_ms=(round(max(latency_samples_ms), 3) if latency_samples_ms else None),
        ring=ring,
        attempts=attempts,
        pending_skip_counts=pending_skip_counts,
        per_server=per_server,
        per_host=per_host,
    )


def render_ring(ring: list[SchedulerTarget], *, console: Console) -> None:
    table = Table(title="Scheduler Ring")
    table.add_column("Slot", justify="right")
    table.add_column("Endpoint", style="cyan")
    table.add_column("Stable ID")
    table.add_column("Group")
    for index, target in enumerate(ring, start=1):
        table.add_row(
            str(index),
            target.endpoint,
            target.stable_id,
            target.group_name or "-",
        )
    console.print(table)


def render_summary(
    summary: SchedulerSummary,
    *,
    console: Console,
    offender_limit: int = DEFAULT_OFFENDER_LIMIT,
) -> None:
    timeout_rate = (
        summary.timeout_attempts / summary.total_launches if summary.total_launches else 0.0
    )
    info_timeout_rate = (
        summary.info_timeout_attempts / summary.total_launches
        if summary.total_launches
        else 0.0
    )
    players_timeout_rate = (
        summary.players_timeout_attempts / summary.total_launches
        if summary.total_launches
        else 0.0
    )

    summary_table = Table(title="Cursor-Scheduled A2S Verification Summary")
    summary_table.add_column("Metric", style="cyan")
    summary_table.add_column("Value", justify="right")
    summary_table.add_row("Started", summary.started_at.isoformat())
    summary_table.add_row("Completed", summary.completed_at.isoformat())
    summary_table.add_row("Targets", str(summary.target_count))
    summary_table.add_row("Tick spacing", f"{summary.tick_spacing_seconds:.3f}s")
    summary_table.add_row("Info timeout", f"{summary.info_timeout_seconds:.1f}s")
    summary_table.add_row("Players timeout", f"{summary.players_timeout_seconds:.1f}s")
    summary_table.add_row("Total launches", str(summary.total_launches))
    summary_table.add_row("Successful attempts", str(summary.successful_attempts))
    summary_table.add_row("Timeouts", str(summary.timeout_attempts))
    summary_table.add_row("Other failures", str(summary.other_failures))
    summary_table.add_row("Info timeout rate", _format_rate(info_timeout_rate))
    summary_table.add_row("Players timeout rate", _format_rate(players_timeout_rate))
    summary_table.add_row("Overall timeout rate", _format_rate(timeout_rate))
    summary_table.add_row("Pending skips", str(summary.pending_skip_count))
    summary_table.add_row("Average response time", _format_latency(summary.avg_latency_ms))
    summary_table.add_row("Longest response time", _format_latency(summary.max_latency_ms))
    console.print(summary_table)

    server_offenders: list[ServerAggregate] = [
        aggregate
        for aggregate in summary.per_server
        if aggregate.timeouts > 0 or aggregate.pending_skips > 0
    ][:offender_limit]
    if server_offenders:
        table = Table(title="Per-Server Timeout / Pending Offenders")
        table.add_column("Endpoint", style="cyan")
        table.add_column("Attempts", justify="right")
        table.add_column("Timeouts", justify="right")
        table.add_column("Info TO", justify="right")
        table.add_column("Players TO", justify="right")
        table.add_column("Pending Skips", justify="right")
        table.add_column("Timeout Rate", justify="right")
        table.add_column("Avg Latency", justify="right")
        for aggregate in server_offenders:
            table.add_row(
                aggregate.target.endpoint,
                str(aggregate.attempts),
                str(aggregate.timeouts),
                str(aggregate.info_timeouts),
                str(aggregate.players_timeouts),
                str(aggregate.pending_skips),
                _format_rate(aggregate.timeout_rate),
                _format_latency(aggregate.avg_latency_ms),
            )
        console.print(table)

    host_offenders: list[HostAggregate] = [
        aggregate
        for aggregate in summary.per_host
        if aggregate.timeouts > 0 or aggregate.pending_skips > 0
    ][:offender_limit]
    if host_offenders:
        table = Table(title="Per-Host Timeout / Pending Offenders")
        table.add_column("Host", style="cyan")
        table.add_column("Endpoints", justify="right")
        table.add_column("Attempts", justify="right")
        table.add_column("Timeouts", justify="right")
        table.add_column("Pending Skips", justify="right")
        table.add_column("Timeout Rate", justify="right")
        for host_aggregate in host_offenders:
            table.add_row(
                host_aggregate.host,
                str(len(host_aggregate.endpoints)),
                str(host_aggregate.attempts),
                str(host_aggregate.timeouts),
                str(host_aggregate.pending_skips),
                _format_rate(host_aggregate.timeout_rate),
            )
        console.print(table)


def summary_to_json_dict(summary: SchedulerSummary) -> dict[str, Any]:
    return {
        "api_url": summary.api_url,
        "configured_duration_seconds": summary.configured_duration_seconds,
        "interval_seconds": summary.interval_seconds,
        "info_timeout_seconds": summary.info_timeout_seconds,
        "players_timeout_seconds": summary.players_timeout_seconds,
        "started_at": summary.started_at.isoformat(),
        "completed_at": summary.completed_at.isoformat(),
        "target_count": summary.target_count,
        "tick_spacing_seconds": summary.tick_spacing_seconds,
        "total_launches": summary.total_launches,
        "successful_attempts": summary.successful_attempts,
        "timeout_attempts": summary.timeout_attempts,
        "other_failures": summary.other_failures,
        "info_timeout_attempts": summary.info_timeout_attempts,
        "players_timeout_attempts": summary.players_timeout_attempts,
        "pending_skip_count": summary.pending_skip_count,
        "avg_latency_ms": summary.avg_latency_ms,
        "max_latency_ms": summary.max_latency_ms,
        "ring": [
            {
                "slot_index": index,
                "host": target.host,
                "port": target.port,
                "endpoint": target.endpoint,
                "hostname": target.hostname,
                "country": target.country,
                "group_name": target.group_name,
                "group_custom_id": target.group_custom_id,
                "server_id": target.server_id,
                "stable_id": target.stable_id,
            }
            for index, target in enumerate(summary.ring)
        ],
        "attempts": [
            {
                "stable_id": attempt.stable_id,
                "host": attempt.host,
                "port": attempt.port,
                "endpoint": attempt.endpoint,
                "hostname": attempt.hostname,
                "country": attempt.country,
                "group_name": attempt.group_name,
                "slot_index": attempt.slot_index,
                "started_at": attempt.started_at.isoformat(),
                "completed_at": attempt.completed_at.isoformat(),
                "elapsed_ms": attempt.elapsed_ms,
                "info_elapsed_ms": attempt.info_elapsed_ms,
                "players_elapsed_ms": attempt.players_elapsed_ms,
                "players_queried": attempt.players_queried,
                "players_returned": attempt.players_returned,
                "success": attempt.success,
                "timed_out": attempt.timed_out,
                "failure_stage": attempt.failure_stage,
                "error": attempt.error,
            }
            for attempt in summary.attempts
        ],
        "pending_skip_counts": summary.pending_skip_counts,
        "per_server": [
            {
                "stable_id": aggregate.target.stable_id,
                "host": aggregate.target.host,
                "port": aggregate.target.port,
                "endpoint": aggregate.target.endpoint,
                "hostname": aggregate.target.hostname,
                "country": aggregate.target.country,
                "group_name": aggregate.target.group_name,
                "group_custom_id": aggregate.target.group_custom_id,
                "server_id": aggregate.target.server_id,
                "attempts": aggregate.attempts,
                "successes": aggregate.successes,
                "timeouts": aggregate.timeouts,
                "other_failures": aggregate.other_failures,
                "info_timeouts": aggregate.info_timeouts,
                "players_timeouts": aggregate.players_timeouts,
                "pending_skips": aggregate.pending_skips,
                "timeout_rate": aggregate.timeout_rate,
                "avg_latency_ms": aggregate.avg_latency_ms,
                "max_latency_ms": aggregate.max_latency_ms,
            }
            for aggregate in summary.per_server
        ],
        "per_host": [
            {
                "host": aggregate.host,
                "endpoints": aggregate.endpoints,
                "attempts": aggregate.attempts,
                "successes": aggregate.successes,
                "timeouts": aggregate.timeouts,
                "other_failures": aggregate.other_failures,
                "info_timeouts": aggregate.info_timeouts,
                "players_timeouts": aggregate.players_timeouts,
                "pending_skips": aggregate.pending_skips,
                "timeout_rate": aggregate.timeout_rate,
                "avg_latency_ms": aggregate.avg_latency_ms,
                "max_latency_ms": aggregate.max_latency_ms,
            }
            for aggregate in summary.per_host
        ],
    }


def write_summary_json(summary: SchedulerSummary, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(summary_to_json_dict(summary), indent=2),
        encoding="utf-8",
    )


async def run_scheduler_command(
    *,
    api_url: str,
    duration_seconds: int,
    interval_seconds: float,
    timeout_seconds: float,
    players_timeout_seconds: float,
    output_json: Path | None,
    limit_servers: int | None,
    verbose_ring: bool,
    console: Console,
    query_fn: QueryServerA2SFn = query_server_a2s,
    fetch_targets_fn: FetchTargetsFn = fetch_online_targets,
    sleep: SleepFn = _default_sleep,
    monotonic: Callable[[], float] = time.monotonic,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> SchedulerSummary:
    targets = await fetch_targets_fn(api_url)
    targets.sort(key=lambda item: item.stable_id)
    if limit_servers is not None:
        targets = targets[:limit_servers]
    if not targets:
        raise ValueError("No scheduler targets remain after applying filters")

    ring = build_scheduler_ring(targets)
    tick_spacing = compute_tick_spacing(interval_seconds, len(ring))
    console.print(f"Loaded {len(targets)} online servers from {api_url}.")
    console.print(
        " | ".join(
            [
                "Scheduler configured",
                f"duration {duration_seconds}s",
                f"interval {interval_seconds:.1f}s",
                f"info timeout {timeout_seconds:.1f}s",
                f"players timeout {players_timeout_seconds:.1f}s",
                f"tick spacing {tick_spacing:.3f}s",
            ]
        )
    )
    if verbose_ring:
        render_ring(ring, console=console)

    summary = await run_scheduler_benchmark(
        api_url=api_url,
        targets=targets,
        duration_seconds=duration_seconds,
        interval_seconds=interval_seconds,
        timeout_seconds=timeout_seconds,
        players_timeout_seconds=players_timeout_seconds,
        query_fn=query_fn,
        sleep=sleep,
        monotonic=monotonic,
        now=now,
        progress_message=console.print,
    )
    render_summary(summary, console=console)
    if output_json is not None:
        write_summary_json(summary, output_json)
        console.print(f"Wrote raw scheduler results to {output_json}.")
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify a cursor-scheduled A2S query strategy against the live GOKZ server fleet."
    )
    parser.add_argument(
        "--duration-seconds",
        type=int,
        default=DEFAULT_DURATION_SECONDS,
        help="How long to keep launching scheduled queries. Default: 300.",
    )
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=DEFAULT_INTERVAL_SECONDS,
        help="Target time for one full cursor sweep across the ring. Default: 10.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="Per-server A2S INFO timeout in seconds. Default: 10.",
    )
    parser.add_argument(
        "--players-timeout-seconds",
        type=float,
        help="Per-server A2S PLAYERS timeout in seconds. Defaults to --timeout-seconds.",
    )
    parser.add_argument(
        "--api-url",
        default=DEFAULT_API_URL,
        help="Public server API URL to fetch scheduler targets from.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        help="Optional path to write raw scheduler results as JSON.",
    )
    parser.add_argument(
        "--limit-servers",
        type=int,
        help="Optional deterministic cap on how many sorted targets to include.",
    )
    parser.add_argument(
        "--verbose-ring",
        action="store_true",
        help="Print the full ring order before the run starts.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    console = Console()
    players_timeout_seconds = (
        args.players_timeout_seconds
        if args.players_timeout_seconds is not None
        else args.timeout_seconds
    )

    try:
        asyncio.run(
            run_scheduler_command(
                api_url=args.api_url,
                duration_seconds=args.duration_seconds,
                interval_seconds=args.interval_seconds,
                timeout_seconds=args.timeout_seconds,
                players_timeout_seconds=players_timeout_seconds,
                output_json=args.output_json,
                limit_servers=args.limit_servers,
                verbose_ring=args.verbose_ring,
                console=console,
            )
        )
    except KeyboardInterrupt:
        console.print("Scheduler verification interrupted by user.")
        return 130
    except Exception as exc:
        console.print(f"Scheduler verification failed: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
