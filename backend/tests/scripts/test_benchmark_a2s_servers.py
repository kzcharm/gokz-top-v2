from __future__ import annotations

import asyncio
import importlib.util
import io
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from rich.console import Console

MODULE_PATH = (
    Path(__file__).resolve().parents[3] / "scripts" / "benchmark_a2s_servers.py"
)
MODULE_SPEC = importlib.util.spec_from_file_location(
    "benchmark_a2s_servers",
    MODULE_PATH,
)
assert MODULE_SPEC is not None
assert MODULE_SPEC.loader is not None
benchmark_a2s_servers = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = benchmark_a2s_servers
MODULE_SPEC.loader.exec_module(benchmark_a2s_servers)


def _target(
    *,
    host: str = "127.0.0.1",
    port: int = 27015,
    hostname: str | None = "Test Server",
) -> benchmark_a2s_servers.BenchmarkTarget:
    return benchmark_a2s_servers.BenchmarkTarget(
        host=host,
        port=port,
        hostname=hostname,
        country="SE",
        group_name="Test Group",
        group_custom_id="test-group",
        server_id=f"{host}:{port}",
    )


def _attempt(
    *,
    endpoint: str,
    round_index: int = 1,
    elapsed_ms: float = 100.0,
    success: bool = True,
    timed_out: bool = False,
    error: str | None = None,
) -> benchmark_a2s_servers.ProbeAttempt:
    started_at = datetime(2026, 5, 11, 9, 0, 0, tzinfo=UTC)
    return benchmark_a2s_servers.ProbeAttempt(
        round_index=round_index,
        endpoint=endpoint,
        hostname="Server",
        country="SE",
        group_name="Group",
        started_at=started_at,
        completed_at=started_at,
        elapsed_ms=elapsed_ms,
        info_elapsed_ms=elapsed_ms if success else None,
        players_elapsed_ms=None,
        players_queried=False,
        players_returned=None,
        success=success,
        timed_out=timed_out,
        failure_stage="info" if (not success and timed_out) else None,
        error=error,
    )


def test_parse_public_server_payload_filters_online_and_dedupes() -> None:
    payload = {
        "data": [
            {
                "host": "1.1.1.1",
                "port": 27015,
                "hostname": "Online A",
                "country": "SE",
                "group_name": "Group A",
                "group_custom_id": "group-a",
                "server_id": "server-a",
                "is_online": True,
            },
            {
                "host": "1.1.1.1",
                "port": 27015,
                "hostname": "Duplicate",
                "country": "SE",
                "group_name": "Group A",
                "group_custom_id": "group-a",
                "server_id": "server-a-dup",
                "is_online": True,
            },
            {
                "host": "2.2.2.2",
                "port": 27016,
                "hostname": "Offline",
                "is_online": False,
            },
            {
                "host": "3.3.3.3",
                "port": 27017,
                "hostname": "Online B",
                "country": "DE",
                "group_name": "Group B",
                "group_custom_id": "group-b",
                "server_id": "server-b",
                "is_online": True,
            },
        ]
    }

    targets = benchmark_a2s_servers.parse_public_server_payload(payload)

    assert [target.endpoint for target in targets] == ["1.1.1.1:27015", "3.3.3.3:27017"]
    assert targets[0].hostname == "Online A"


def test_build_benchmark_summary_successful_only() -> None:
    target = _target()
    attempts = [
        _attempt(endpoint=target.endpoint, elapsed_ms=100.0),
        _attempt(endpoint=target.endpoint, round_index=2, elapsed_ms=300.0),
    ]

    summary = benchmark_a2s_servers.build_benchmark_summary(
        api_url="https://example.com",
        configured_duration_seconds=300,
        interval_seconds=10.0,
        info_timeout_seconds=30.0,
        players_timeout_seconds=30.0,
        started_at=datetime(2026, 5, 11, 9, 0, 0, tzinfo=UTC),
        completed_at=datetime(2026, 5, 11, 9, 5, 0, tzinfo=UTC),
        targets=[target],
        attempts=attempts,
        round_count=2,
    )

    assert summary.avg_latency_ms == 200.0
    assert summary.max_latency_ms == 300.0
    assert summary.timeout_attempts == 0
    assert summary.per_server[0].timeout_rate == 0.0
    assert summary.per_server[0].avg_latency_ms == 200.0


def test_build_benchmark_summary_mixed_success_and_timeouts() -> None:
    target = _target()
    attempts = [
        _attempt(endpoint=target.endpoint, elapsed_ms=150.0),
        _attempt(
            endpoint=target.endpoint,
            round_index=2,
            elapsed_ms=30_000.0,
            success=False,
            timed_out=True,
            error="timeout",
        ),
        _attempt(endpoint=target.endpoint, round_index=3, elapsed_ms=250.0),
    ]

    summary = benchmark_a2s_servers.build_benchmark_summary(
        api_url="https://example.com",
        configured_duration_seconds=300,
        interval_seconds=10.0,
        info_timeout_seconds=30.0,
        players_timeout_seconds=30.0,
        started_at=datetime(2026, 5, 11, 9, 0, 0, tzinfo=UTC),
        completed_at=datetime(2026, 5, 11, 9, 5, 0, tzinfo=UTC),
        targets=[target],
        attempts=attempts,
        round_count=3,
    )

    assert summary.avg_latency_ms == 200.0
    assert summary.max_latency_ms == 250.0
    assert summary.timeout_attempts == 1
    assert summary.per_server[0].timeout_rate == pytest.approx(1 / 3)


def test_build_benchmark_summary_all_timeout_server() -> None:
    target = _target()
    attempts = [
        _attempt(
            endpoint=target.endpoint,
            elapsed_ms=30_000.0,
            success=False,
            timed_out=True,
            error="timeout",
        ),
        _attempt(
            endpoint=target.endpoint,
            round_index=2,
            elapsed_ms=30_000.0,
            success=False,
            timed_out=True,
            error="timeout",
        ),
    ]

    summary = benchmark_a2s_servers.build_benchmark_summary(
        api_url="https://example.com",
        configured_duration_seconds=300,
        interval_seconds=10.0,
        info_timeout_seconds=30.0,
        players_timeout_seconds=30.0,
        started_at=datetime(2026, 5, 11, 9, 0, 0, tzinfo=UTC),
        completed_at=datetime(2026, 5, 11, 9, 5, 0, tzinfo=UTC),
        targets=[target],
        attempts=attempts,
        round_count=2,
    )

    assert summary.avg_latency_ms is None
    assert summary.max_latency_ms is None
    assert summary.per_server[0].avg_latency_ms is None
    assert summary.per_server[0].max_latency_ms is None
    assert summary.per_server[0].timeout_rate == 1.0


@pytest.mark.asyncio
async def test_request_a2s_protocol_closes_transport_on_error(monkeypatch) -> None:
    class _FakeTransport:
        def __init__(self) -> None:
            self.close_calls = 0

        def close(self) -> None:
            self.close_calls += 1

    class _FakeConn:
        def __init__(self, transport: _FakeTransport) -> None:
            self.transport = transport

    transport = _FakeTransport()
    conn = _FakeConn(transport)

    async def _fake_create(
        address: tuple[str, int],
        timeout: float,
    ) -> _FakeConn:
        assert address == ("127.0.0.1", 27015)
        assert timeout == 5.0
        return conn

    async def _fake_request_async_impl(
        connection: _FakeConn,
        encoding: str,
        protocol: type[object],
    ) -> None:
        assert connection is conn
        assert encoding == "utf-8"
        assert protocol is object
        raise TimeoutError("boom")

    monkeypatch.setattr(
        benchmark_a2s_servers.A2SStreamAsync,
        "create",
        _fake_create,
    )
    monkeypatch.setattr(
        benchmark_a2s_servers,
        "request_async_impl",
        _fake_request_async_impl,
    )

    with pytest.raises(TimeoutError, match="boom"):
        await benchmark_a2s_servers.request_a2s_protocol(
            address=("127.0.0.1", 27015),
            timeout=5.0,
            encoding="utf-8",
            protocol=object,
        )

    assert transport.close_calls == 1
    assert isinstance(conn.transport, benchmark_a2s_servers._ClosedTransport)


@pytest.mark.asyncio
async def test_run_benchmark_round_waits_for_all_servers() -> None:
    first_started = asyncio.Event()
    second_started = asyncio.Event()
    first_release = asyncio.Event()
    second_release = asyncio.Event()

    async def _fake_query_server_a2s_info(
        *,
        ip: str,
        port: int,
        timeout: float,
        players_timeout: float,
    ) -> benchmark_a2s_servers.ProbeQueryResult:
        del timeout, players_timeout
        if ip == "127.0.0.1" and port == 27015:
            first_started.set()
            await first_release.wait()
        else:
            second_started.set()
            await second_release.wait()
        return benchmark_a2s_servers.ProbeQueryResult(
            map_name="kz_test",
            player_count=0,
            info_elapsed_ms=100.0,
            players_elapsed_ms=None,
            players_queried=False,
            players_returned=None,
        )

    task = asyncio.create_task(
        benchmark_a2s_servers.run_benchmark_round(
            round_index=1,
            targets=[_target(), _target(host="127.0.0.2", port=27016)],
            timeout_seconds=30.0,
            players_timeout_seconds=30.0,
            query_fn=_fake_query_server_a2s_info,
        )
    )

    await first_started.wait()
    await second_started.wait()
    first_release.set()
    await asyncio.sleep(0)
    assert task.done() is False

    second_release.set()
    attempts = await task

    assert len(attempts) == 2
    assert all(attempt.success for attempt in attempts)


class _FakeClock:
    def __init__(self) -> None:
        self.current = 0.0
        self.sleep_calls: list[float] = []

    def monotonic(self) -> float:
        return self.current

    async def sleep(self, seconds: float) -> None:
        self.sleep_calls.append(seconds)
        self.current += seconds


@pytest.mark.asyncio
async def test_run_benchmark_only_sleeps_after_fast_rounds() -> None:
    clock = _FakeClock()
    target = _target()
    round_durations = iter([4.0, 12.0])

    async def _fake_run_round(
        round_index: int,
        targets: list[benchmark_a2s_servers.BenchmarkTarget],
        timeout_seconds: float,
        players_timeout_seconds: float,
    ) -> list[benchmark_a2s_servers.ProbeAttempt]:
        del targets, timeout_seconds, players_timeout_seconds
        clock.current += next(round_durations)
        return [
            _attempt(
                endpoint=target.endpoint,
                round_index=round_index,
                elapsed_ms=100.0,
            )
        ]

    summary = await benchmark_a2s_servers.run_benchmark(
        api_url="https://example.com",
        targets=[target],
        duration_seconds=22,
        interval_seconds=10.0,
        timeout_seconds=30.0,
        players_timeout_seconds=30.0,
        query_fn=_fake_query_server_a2s_info_success,
        run_round=_fake_run_round,
        sleep=clock.sleep,
        monotonic=clock.monotonic,
        now=lambda: datetime(2026, 5, 11, 9, 0, 0, tzinfo=UTC),
    )

    assert summary.round_count == 2
    assert clock.sleep_calls == [6.0]


async def _fake_query_server_a2s_info_success(
    *,
    ip: str,
    port: int,
    timeout: float,
    players_timeout: float,
) -> benchmark_a2s_servers.ProbeQueryResult:
    del ip, port, timeout, players_timeout
    return benchmark_a2s_servers.ProbeQueryResult(
        map_name="kz_test",
        player_count=0,
        info_elapsed_ms=100.0,
        players_elapsed_ms=None,
        players_queried=False,
        players_returned=None,
    )


@pytest.mark.asyncio
async def test_run_benchmark_command_with_mocked_payload_and_query(
    tmp_path,
) -> None:
    payload = {
        "data": [
            {
                "host": "10.0.0.1",
                "port": 27015,
                "hostname": "One",
                "country": "SE",
                "group_name": "Group",
                "group_custom_id": "group",
                "server_id": "one",
                "is_online": True,
            },
            {
                "host": "10.0.0.1",
                "port": 27015,
                "hostname": "One Duplicate",
                "country": "SE",
                "group_name": "Group",
                "group_custom_id": "group",
                "server_id": "one-dup",
                "is_online": True,
            },
            {
                "host": "10.0.0.2",
                "port": 27016,
                "hostname": "Two",
                "country": "DE",
                "group_name": "Group 2",
                "group_custom_id": "group-2",
                "server_id": "two",
                "is_online": True,
            },
            {
                "host": "10.0.0.3",
                "port": 27017,
                "hostname": "Offline",
                "is_online": False,
            },
        ]
    }
    seen_queries: list[tuple[str, int, float, float]] = []
    console_output = io.StringIO()
    console = Console(file=console_output, force_terminal=False, color_system=None)
    clock = _FakeClock()
    output_path = tmp_path / "benchmark.json"

    async def _fake_fetch_targets(
        api_url: str,
    ) -> list[benchmark_a2s_servers.BenchmarkTarget]:
        assert api_url == "https://example.com/public-servers"
        return benchmark_a2s_servers.parse_public_server_payload(payload)

    async def _fake_query(
        *,
        ip: str,
        port: int,
        timeout: float,
        players_timeout: float,
    ) -> benchmark_a2s_servers.ProbeQueryResult:
        seen_queries.append((ip, port, timeout, players_timeout))
        return benchmark_a2s_servers.ProbeQueryResult(
            map_name="kz_test",
            player_count=0,
            info_elapsed_ms=100.0,
            players_elapsed_ms=None,
            players_queried=False,
            players_returned=None,
        )

    summary = await benchmark_a2s_servers.run_benchmark_command(
        api_url="https://example.com/public-servers",
        duration_seconds=1,
        interval_seconds=10.0,
        timeout_seconds=30.0,
        players_timeout_seconds=30.0,
        output_json=output_path,
        console=console,
        query_fn=_fake_query,
        fetch_targets_fn=_fake_fetch_targets,
        sleep=clock.sleep,
        monotonic=clock.monotonic,
        now=lambda: datetime(2026, 5, 11, 9, 0, 0, tzinfo=UTC),
    )

    assert summary.target_count == 2
    assert summary.total_attempts == 2
    assert seen_queries == [
        ("10.0.0.1", 27015, 30.0, 30.0),
        ("10.0.0.2", 27016, 30.0, 30.0),
    ]

    output_payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert output_payload["target_count"] == 2
    assert output_payload["total_attempts"] == 2
    output_text = console_output.getvalue()
    assert "Loaded 2 online servers" in output_text
    assert "Benchmark configured | duration 1s | interval 10.0s | info timeout 30.0s" in output_text
    assert "players timeout 30.0s" in output_text
    assert "concurrency 2" in output_text
    assert "Round 1 started | targets 2 | info timeout 30.0s" in output_text
    assert "players timeout 30.0s" in output_text
    assert "interval 10.0s" in output_text
    assert "Round 1 finished | ok 2 | timeouts 0 | other failures 0" in output_text
