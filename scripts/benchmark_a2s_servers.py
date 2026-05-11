#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import time
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
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_WORST_OFFENDER_LIMIT = 10
ROUND_PROGRESS_HEARTBEAT_SECONDS = 5.0
ROUND_PROGRESS_STEP = 10

class QueryServerA2SInfoFn(Protocol):
    async def __call__(
        self,
        *,
        ip: str,
        port: int,
        timeout: float,
        players_timeout: float,
    ) -> ProbeQueryResult: ...


class RunRoundFn(Protocol):
    async def __call__(
        self,
        round_index: int,
        targets: list[BenchmarkTarget],
        timeout_seconds: float,
        players_timeout_seconds: float,
    ) -> list[ProbeAttempt]: ...


class FetchTargetsFn(Protocol):
    async def __call__(self, api_url: str) -> list[BenchmarkTarget]: ...

type SleepFn = Callable[[float], Awaitable[None]]
type ProgressMessageFn = Callable[[str], None]


@dataclass(slots=True, frozen=True)
class BenchmarkTarget:
    host: str
    port: int
    hostname: str | None
    country: str | None
    group_name: str | None
    group_custom_id: str | None
    server_id: str | None

    @property
    def endpoint(self) -> str:
        return f"{self.host}:{self.port}"

    @property
    def display_name(self) -> str:
        return self.hostname or self.endpoint


@dataclass(slots=True, frozen=True)
class ProbeAttempt:
    round_index: int
    endpoint: str
    hostname: str | None
    country: str | None
    group_name: str | None
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
class ServerAggregate:
    target: BenchmarkTarget
    attempts: int
    successes: int
    timeouts: int
    other_failures: int
    timeout_rate: float
    avg_latency_ms: float | None
    max_latency_ms: float | None


@dataclass(slots=True, frozen=True)
class BenchmarkSummary:
    api_url: str
    configured_duration_seconds: int
    interval_seconds: float
    info_timeout_seconds: float
    players_timeout_seconds: float
    started_at: datetime
    completed_at: datetime
    target_count: int
    round_count: int
    total_attempts: int
    successful_attempts: int
    timeout_attempts: int
    other_failures: int
    avg_latency_ms: float | None
    max_latency_ms: float | None
    targets: list[BenchmarkTarget]
    attempts: list[ProbeAttempt]
    per_server: list[ServerAggregate]


class _ClosedTransport:
    def close(self) -> None:
        return


def _ensure_int(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"Expected {field_name} to be an integer")
    return int(value)


def parse_public_server_payload(payload: dict[str, Any]) -> list[BenchmarkTarget]:
    rows = payload.get("data")
    if not isinstance(rows, list):
        raise ValueError("Expected API payload to include a list in 'data'")

    deduped_targets: list[BenchmarkTarget] = []
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
        deduped_targets.append(
            BenchmarkTarget(
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
                server_id=row.get("server_id")
                if isinstance(row.get("server_id"), str)
                else None,
            )
        )

    return deduped_targets


async def fetch_online_targets(api_url: str) -> list[BenchmarkTarget]:
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


def compute_round_sleep_seconds(
    *,
    round_elapsed_seconds: float,
    interval_seconds: float,
    remaining_seconds: float,
) -> float:
    interval_gap = max(0.0, interval_seconds - round_elapsed_seconds)
    if interval_gap <= 0.0 or remaining_seconds <= 0.0:
        return 0.0
    return min(interval_gap, remaining_seconds)


async def _default_sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


async def run_benchmark_round(
    *,
    round_index: int,
    targets: list[BenchmarkTarget],
    timeout_seconds: float,
    players_timeout_seconds: float,
    query_fn: QueryServerA2SInfoFn,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    monotonic: Callable[[], float] = time.monotonic,
    progress_message: ProgressMessageFn | None = None,
) -> list[ProbeAttempt]:
    async def _probe_target(target: BenchmarkTarget) -> ProbeAttempt:
        started_at = now()
        started_monotonic = monotonic()
        try:
            result = await query_fn(
                ip=target.host,
                port=target.port,
                timeout=timeout_seconds,
                players_timeout=players_timeout_seconds,
            )
        except ProbeQueryError as exc:
            completed_at = now()
            elapsed_ms = (monotonic() - started_monotonic) * 1000
            cause = exc.__cause__
            error_message = (
                str(cause).strip()
                if cause is not None and str(cause).strip()
                else exc.__class__.__name__
            )
            return ProbeAttempt(
                round_index=round_index,
                endpoint=target.endpoint,
                hostname=target.hostname,
                country=target.country,
                group_name=target.group_name,
                started_at=started_at,
                completed_at=completed_at,
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
            completed_at = now()
            elapsed_ms = (monotonic() - started_monotonic) * 1000
            error_message = str(exc).strip() or exc.__class__.__name__
            return ProbeAttempt(
                round_index=round_index,
                endpoint=target.endpoint,
                hostname=target.hostname,
                country=target.country,
                group_name=target.group_name,
                started_at=started_at,
                completed_at=completed_at,
                elapsed_ms=round(elapsed_ms, 3),
                info_elapsed_ms=None,
                players_elapsed_ms=None,
                players_queried=False,
                players_returned=None,
                success=False,
                timed_out=is_timeout_error(exc),
                failure_stage=None,
                error=error_message,
            )

        completed_at = now()
        elapsed_ms = (monotonic() - started_monotonic) * 1000
        return ProbeAttempt(
            round_index=round_index,
            endpoint=target.endpoint,
            hostname=target.hostname,
            country=target.country,
            group_name=target.group_name,
            started_at=started_at,
            completed_at=completed_at,
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

    attempts: list[ProbeAttempt] = []
    total_targets = len(targets)
    completed_count = 0
    success_count = 0
    timeout_count = 0
    other_failure_count = 0
    round_started_monotonic = monotonic()
    reporter_done = asyncio.Event()

    async def _heartbeat_reporter() -> None:
        while not reporter_done.is_set():
            await asyncio.sleep(ROUND_PROGRESS_HEARTBEAT_SECONDS)
            if reporter_done.is_set() or progress_message is None:
                continue
            progress_message(
                " | ".join(
                    [
                        f"Round {round_index} waiting",
                        f"{completed_count}/{total_targets} complete",
                        f"ok {success_count}",
                        f"timeouts {timeout_count}",
                        f"other failures {other_failure_count}",
                        f"elapsed {monotonic() - round_started_monotonic:.1f}s",
                    ]
                )
            )

    reporter_task = (
        asyncio.create_task(_heartbeat_reporter()) if progress_message is not None else None
    )
    probe_tasks = [asyncio.create_task(_probe_target(target)) for target in targets]

    try:
        for completed_probe in asyncio.as_completed(probe_tasks):
            attempt = await completed_probe
            attempts.append(attempt)
            completed_count += 1
            if attempt.success:
                success_count += 1
            elif attempt.timed_out:
                timeout_count += 1
            else:
                other_failure_count += 1

            if progress_message is None:
                continue

            should_emit = (
                completed_count == total_targets
                or completed_count % ROUND_PROGRESS_STEP == 0
                or not attempt.success
            )
            if should_emit:
                progress_message(
                    " | ".join(
                        [
                            f"Round {round_index} progress",
                            f"{completed_count}/{total_targets} complete",
                            f"ok {success_count}",
                            f"timeouts {timeout_count}",
                            f"other failures {other_failure_count}",
                            f"elapsed {monotonic() - round_started_monotonic:.1f}s",
                            f"last {_format_attempt_status(attempt)}",
                        ]
                    )
                )
    finally:
        reporter_done.set()
        if reporter_task is not None:
            reporter_task.cancel()
            with suppress(asyncio.CancelledError):
                await reporter_task

    return attempts


def build_benchmark_summary(
    *,
    api_url: str,
    configured_duration_seconds: int,
    interval_seconds: float,
    info_timeout_seconds: float,
    players_timeout_seconds: float,
    started_at: datetime,
    completed_at: datetime,
    targets: list[BenchmarkTarget],
    attempts: list[ProbeAttempt],
    round_count: int,
) -> BenchmarkSummary:
    by_endpoint = {target.endpoint: target for target in targets}
    per_server: list[ServerAggregate] = []
    latency_samples_ms = [attempt.elapsed_ms for attempt in attempts if attempt.success]
    timeout_attempts = sum(1 for attempt in attempts if attempt.timed_out)
    successful_attempts = sum(1 for attempt in attempts if attempt.success)
    other_failures = sum(
        1 for attempt in attempts if not attempt.success and not attempt.timed_out
    )

    for endpoint, target in by_endpoint.items():
        server_attempts = [attempt for attempt in attempts if attempt.endpoint == endpoint]
        successes = [attempt.elapsed_ms for attempt in server_attempts if attempt.success]
        timeouts = sum(1 for attempt in server_attempts if attempt.timed_out)
        attempts_count = len(server_attempts)
        other_server_failures = sum(
            1
            for attempt in server_attempts
            if not attempt.success and not attempt.timed_out
        )
        per_server.append(
            ServerAggregate(
                target=target,
                attempts=attempts_count,
                successes=len(successes),
                timeouts=timeouts,
                other_failures=other_server_failures,
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

    return BenchmarkSummary(
        api_url=api_url,
        configured_duration_seconds=configured_duration_seconds,
        interval_seconds=interval_seconds,
        info_timeout_seconds=info_timeout_seconds,
        players_timeout_seconds=players_timeout_seconds,
        started_at=started_at,
        completed_at=completed_at,
        target_count=len(targets),
        round_count=round_count,
        total_attempts=len(attempts),
        successful_attempts=successful_attempts,
        timeout_attempts=timeout_attempts,
        other_failures=other_failures,
        avg_latency_ms=(
            round(sum(latency_samples_ms) / len(latency_samples_ms), 3)
            if latency_samples_ms
            else None
        ),
        max_latency_ms=(round(max(latency_samples_ms), 3) if latency_samples_ms else None),
        targets=targets,
        attempts=attempts,
        per_server=per_server,
    )


async def run_benchmark(
    *,
    api_url: str,
    targets: list[BenchmarkTarget],
    duration_seconds: int,
    interval_seconds: float,
    timeout_seconds: float,
    players_timeout_seconds: float,
    query_fn: QueryServerA2SInfoFn,
    run_round: RunRoundFn | None = None,
    sleep: SleepFn = _default_sleep,
    monotonic: Callable[[], float] = time.monotonic,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    progress_message: ProgressMessageFn | None = None,
) -> BenchmarkSummary:
    if duration_seconds <= 0:
        raise ValueError("duration_seconds must be greater than zero")
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be greater than zero")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be greater than zero")
    if players_timeout_seconds <= 0:
        raise ValueError("players_timeout_seconds must be greater than zero")
    if not targets:
        raise ValueError("At least one benchmark target is required")

    attempts: list[ProbeAttempt] = []
    started_at = now()
    deadline = monotonic() + duration_seconds
    round_count = 0

    async def _default_run_round(
        round_index: int,
        round_targets: list[BenchmarkTarget],
        round_timeout_seconds: float,
        round_players_timeout_seconds: float,
    ) -> list[ProbeAttempt]:
        return await run_benchmark_round(
            round_index=round_index,
            targets=round_targets,
            timeout_seconds=round_timeout_seconds,
            players_timeout_seconds=round_players_timeout_seconds,
            query_fn=query_fn,
            now=now,
            monotonic=monotonic,
            progress_message=progress_message,
        )

    run_round_fn = run_round or _default_run_round

    while monotonic() < deadline:
        round_count += 1
        if progress_message is not None:
            progress_message(
                " | ".join(
                    [
                        f"Round {round_count} started",
                        f"targets {len(targets)}",
                        f"info timeout {timeout_seconds:.1f}s",
                        f"players timeout {players_timeout_seconds:.1f}s",
                        f"interval {interval_seconds:.1f}s",
                    ]
                )
            )
        round_started_monotonic = monotonic()
        round_attempts = await run_round_fn(
            round_count,
            targets,
            timeout_seconds,
            players_timeout_seconds,
        )
        attempts.extend(round_attempts)
        round_elapsed_seconds = monotonic() - round_started_monotonic
        round_successes = sum(1 for attempt in round_attempts if attempt.success)
        round_timeouts = sum(1 for attempt in round_attempts if attempt.timed_out)
        round_other_failures = sum(
            1
            for attempt in round_attempts
            if not attempt.success and not attempt.timed_out
        )
        remaining_seconds = deadline - monotonic()
        sleep_seconds = compute_round_sleep_seconds(
            round_elapsed_seconds=round_elapsed_seconds,
            interval_seconds=interval_seconds,
            remaining_seconds=remaining_seconds,
        )
        if progress_message is not None:
            next_step_message = (
                f"sleeping {sleep_seconds:.1f}s before next round"
                if sleep_seconds > 0
                else "starting next round immediately"
            )
            progress_message(
                " | ".join(
                    [
                        f"Round {round_count} finished",
                        f"ok {round_successes}",
                        f"timeouts {round_timeouts}",
                        f"other failures {round_other_failures}",
                        f"elapsed {round_elapsed_seconds:.1f}s",
                        next_step_message,
                    ]
                )
            )
        if sleep_seconds > 0:
            await sleep(sleep_seconds)

    completed_at = now()
    return build_benchmark_summary(
        api_url=api_url,
        configured_duration_seconds=duration_seconds,
        interval_seconds=interval_seconds,
        info_timeout_seconds=timeout_seconds,
        players_timeout_seconds=players_timeout_seconds,
        started_at=started_at,
        completed_at=completed_at,
        targets=targets,
        attempts=attempts,
        round_count=round_count,
    )


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
        return f"{attempt.endpoint} timed out after {attempt.elapsed_ms:.1f} ms"
    return f"{attempt.endpoint} failed after {attempt.elapsed_ms:.1f} ms"


def render_summary(
    summary: BenchmarkSummary,
    *,
    console: Console,
    worst_offender_limit: int = DEFAULT_WORST_OFFENDER_LIMIT,
) -> None:
    summary_table = Table(title="A2S Fleet Benchmark Summary")
    summary_table.add_column("Metric", style="cyan")
    summary_table.add_column("Value", justify="right")
    summary_table.add_row("Started", summary.started_at.isoformat())
    summary_table.add_row("Completed", summary.completed_at.isoformat())
    summary_table.add_row("Targets", str(summary.target_count))
    summary_table.add_row("Rounds", str(summary.round_count))
    summary_table.add_row("Info timeout", f"{summary.info_timeout_seconds:.1f}s")
    summary_table.add_row("Players timeout", f"{summary.players_timeout_seconds:.1f}s")
    summary_table.add_row("Total attempts", str(summary.total_attempts))
    summary_table.add_row("Successful attempts", str(summary.successful_attempts))
    summary_table.add_row("Timeouts", str(summary.timeout_attempts))
    summary_table.add_row("Other failures", str(summary.other_failures))
    timeout_rate = (
        summary.timeout_attempts / summary.total_attempts
        if summary.total_attempts
        else 0.0
    )
    summary_table.add_row("Overall timeout rate", _format_rate(timeout_rate))
    summary_table.add_row("Average response time", _format_latency(summary.avg_latency_ms))
    summary_table.add_row("Longest response time", _format_latency(summary.max_latency_ms))
    console.print(summary_table)

    offenders = [
        aggregate for aggregate in summary.per_server if aggregate.timeouts > 0
    ][:worst_offender_limit]
    if not offenders:
        console.print("No timeouts observed during the benchmark.")
        return

    offenders_table = Table(title="Worst Timeout Offenders")
    offenders_table.add_column("Endpoint", style="cyan")
    offenders_table.add_column("Group")
    offenders_table.add_column("Attempts", justify="right")
    offenders_table.add_column("Timeouts", justify="right")
    offenders_table.add_column("Timeout Rate", justify="right")
    offenders_table.add_column("Avg Latency", justify="right")
    offenders_table.add_column("Max Latency", justify="right")

    for aggregate in offenders:
        offenders_table.add_row(
            aggregate.target.endpoint,
            aggregate.target.group_name or "-",
            str(aggregate.attempts),
            str(aggregate.timeouts),
            _format_rate(aggregate.timeout_rate),
            _format_latency(aggregate.avg_latency_ms),
            _format_latency(aggregate.max_latency_ms),
        )

    console.print(offenders_table)


def summary_to_json_dict(summary: BenchmarkSummary) -> dict[str, Any]:
    return {
        "api_url": summary.api_url,
        "configured_duration_seconds": summary.configured_duration_seconds,
        "interval_seconds": summary.interval_seconds,
        "info_timeout_seconds": summary.info_timeout_seconds,
        "players_timeout_seconds": summary.players_timeout_seconds,
        "started_at": summary.started_at.isoformat(),
        "completed_at": summary.completed_at.isoformat(),
        "target_count": summary.target_count,
        "round_count": summary.round_count,
        "total_attempts": summary.total_attempts,
        "successful_attempts": summary.successful_attempts,
        "timeout_attempts": summary.timeout_attempts,
        "other_failures": summary.other_failures,
        "avg_latency_ms": summary.avg_latency_ms,
        "max_latency_ms": summary.max_latency_ms,
        "targets": [
            {
                "host": target.host,
                "port": target.port,
                "endpoint": target.endpoint,
                "hostname": target.hostname,
                "country": target.country,
                "group_name": target.group_name,
                "group_custom_id": target.group_custom_id,
                "server_id": target.server_id,
            }
            for target in summary.targets
        ],
        "attempts": [
            {
                "round_index": attempt.round_index,
                "endpoint": attempt.endpoint,
                "hostname": attempt.hostname,
                "country": attempt.country,
                "group_name": attempt.group_name,
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
        "per_server": [
            {
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
                "timeout_rate": aggregate.timeout_rate,
                "avg_latency_ms": aggregate.avg_latency_ms,
                "max_latency_ms": aggregate.max_latency_ms,
            }
            for aggregate in summary.per_server
        ],
    }


def write_summary_json(summary: BenchmarkSummary, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(summary_to_json_dict(summary), indent=2),
        encoding="utf-8",
    )


async def run_benchmark_command(
    *,
    api_url: str,
    duration_seconds: int,
    interval_seconds: float,
    timeout_seconds: float,
    players_timeout_seconds: float,
    output_json: Path | None,
    console: Console,
    query_fn: QueryServerA2SInfoFn = query_server_a2s,
    fetch_targets_fn: FetchTargetsFn = fetch_online_targets,
    run_round: RunRoundFn | None = None,
    sleep: SleepFn = _default_sleep,
    monotonic: Callable[[], float] = time.monotonic,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> BenchmarkSummary:
    targets = await fetch_targets_fn(api_url)
    console.print(
        f"Loaded {len(targets)} online servers from {api_url}."
    )
    console.print(
        " | ".join(
            [
                "Benchmark configured",
                f"duration {duration_seconds}s",
                f"interval {interval_seconds:.1f}s",
                f"info timeout {timeout_seconds:.1f}s",
                f"players timeout {players_timeout_seconds:.1f}s",
                f"concurrency {len(targets)}",
            ]
        )
    )
    summary = await run_benchmark(
        api_url=api_url,
        targets=targets,
        duration_seconds=duration_seconds,
        interval_seconds=interval_seconds,
        timeout_seconds=timeout_seconds,
        players_timeout_seconds=players_timeout_seconds,
        query_fn=query_fn,
        run_round=run_round,
        sleep=sleep,
        monotonic=monotonic,
        now=now,
        progress_message=console.print,
    )
    render_summary(summary, console=console)
    if output_json is not None:
        write_summary_json(summary, output_json)
        console.print(f"Wrote raw benchmark results to {output_json}.")
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Benchmark A2S response times across the current online GOKZ server fleet."
    )
    parser.add_argument(
        "--duration-seconds",
        type=int,
        default=DEFAULT_DURATION_SECONDS,
        help="How long to keep running benchmark rounds. Default: 300.",
    )
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=DEFAULT_INTERVAL_SECONDS,
        help="Target interval between round starts. Default: 10.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="Per-server A2S INFO timeout in seconds. Default: 30.",
    )
    parser.add_argument(
        "--players-timeout-seconds",
        type=float,
        help="Per-server A2S PLAYER timeout in seconds. Defaults to --timeout-seconds.",
    )
    parser.add_argument(
        "--api-url",
        default=DEFAULT_API_URL,
        help="Public server API URL to fetch benchmark targets from.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        help="Optional path to write raw benchmark results as JSON.",
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
            run_benchmark_command(
                api_url=args.api_url,
                duration_seconds=args.duration_seconds,
                interval_seconds=args.interval_seconds,
                timeout_seconds=args.timeout_seconds,
                players_timeout_seconds=players_timeout_seconds,
                output_json=args.output_json,
                console=console,
            )
        )
    except KeyboardInterrupt:
        console.print("Benchmark interrupted by user.")
        return 130
    except Exception as exc:
        console.print(f"Benchmark failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
