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
    Path(__file__).resolve().parents[3] / "scripts" / "verify_a2s_scheduler.py"
)
MODULE_SPEC = importlib.util.spec_from_file_location(
    "verify_a2s_scheduler",
    MODULE_PATH,
)
assert MODULE_SPEC is not None
assert MODULE_SPEC.loader is not None
verify_a2s_scheduler = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = verify_a2s_scheduler
MODULE_SPEC.loader.exec_module(verify_a2s_scheduler)


def _target(
    *,
    host: str,
    port: int,
    stable_id: str,
    hostname: str | None = None,
) -> verify_a2s_scheduler.SchedulerTarget:
    return verify_a2s_scheduler.SchedulerTarget(
        host=host,
        port=port,
        hostname=hostname or f"{host}:{port}",
        country="SE",
        group_name="Group",
        group_custom_id="group",
        server_id=stable_id,
        stable_id=stable_id,
    )


def _attempt(
    *,
    target: verify_a2s_scheduler.SchedulerTarget,
    elapsed_ms: float = 100.0,
    success: bool = True,
    timed_out: bool = False,
    failure_stage: str | None = None,
) -> verify_a2s_scheduler.ProbeAttempt:
    started_at = datetime(2026, 5, 11, 9, 0, 0, tzinfo=UTC)
    return verify_a2s_scheduler.ProbeAttempt(
        stable_id=target.stable_id,
        host=target.host,
        port=target.port,
        endpoint=target.endpoint,
        hostname=target.hostname,
        country=target.country,
        group_name=target.group_name,
        slot_index=0,
        started_at=started_at,
        completed_at=started_at,
        elapsed_ms=elapsed_ms,
        info_elapsed_ms=elapsed_ms if failure_stage != "players" else 25.0,
        players_elapsed_ms=elapsed_ms if failure_stage == "players" else None,
        players_queried=failure_stage == "players",
        players_returned=None,
        success=success,
        timed_out=timed_out,
        failure_stage=failure_stage,
        error=None if success else "boom",
    )


def test_parse_public_server_payload_stable_id_prefers_server_id() -> None:
    payload = {
        "data": [
            {
                "host": "1.1.1.1",
                "port": 27015,
                "hostname": "One",
                "group_name": "A",
                "group_custom_id": "a",
                "server_id": "0001",
                "is_online": True,
            },
            {
                "host": "2.2.2.2",
                "port": 27016,
                "hostname": "Two",
                "is_online": True,
            },
        ]
    }

    targets = verify_a2s_scheduler.parse_public_server_payload(payload)

    assert targets[0].stable_id == "0001"
    assert targets[1].stable_id == "2.2.2.2:27016"


def test_build_scheduler_ring_spreads_same_ip_targets() -> None:
    targets = [
        _target(host="10.0.0.1", port=27015, stable_id="a-1"),
        _target(host="10.0.0.1", port=27016, stable_id="a-2"),
        _target(host="10.0.0.1", port=27017, stable_id="a-3"),
        _target(host="10.0.0.2", port=27015, stable_id="b-1"),
        _target(host="10.0.0.3", port=27015, stable_id="c-1"),
        _target(host="10.0.0.4", port=27015, stable_id="d-1"),
    ]

    ring = verify_a2s_scheduler.build_scheduler_ring(targets)
    positions = {
        target.stable_id: index
        for index, target in enumerate(ring)
    }

    assert positions["a-1"] == 0
    assert positions["a-2"] == 2
    assert positions["a-3"] == 4
    assert [target.stable_id for target in ring if target.host != "10.0.0.1"] == [
        "b-1",
        "c-1",
        "d-1",
    ]


def test_build_scheduler_ring_is_deterministic() -> None:
    targets = [
        _target(host="10.0.0.3", port=27015, stable_id="c-1"),
        _target(host="10.0.0.1", port=27016, stable_id="a-2"),
        _target(host="10.0.0.2", port=27015, stable_id="b-1"),
        _target(host="10.0.0.1", port=27015, stable_id="a-1"),
    ]

    first = [target.stable_id for target in verify_a2s_scheduler.build_scheduler_ring(targets)]
    second = [target.stable_id for target in verify_a2s_scheduler.build_scheduler_ring(list(reversed(targets)))]

    assert first == second


def test_compute_tick_spacing() -> None:
    assert verify_a2s_scheduler.compute_tick_spacing(10.0, 4) == 2.5


def test_build_scheduler_summary_excludes_timeouts_from_latency() -> None:
    first = _target(host="10.0.0.1", port=27015, stable_id="a-1")
    second = _target(host="10.0.0.2", port=27015, stable_id="b-1")
    attempts = [
        _attempt(target=first, elapsed_ms=100.0),
        _attempt(
            target=second,
            elapsed_ms=10_000.0,
            success=False,
            timed_out=True,
            failure_stage="info",
        ),
    ]

    summary = verify_a2s_scheduler.build_scheduler_summary(
        api_url="https://example.com",
        configured_duration_seconds=30,
        interval_seconds=10.0,
        info_timeout_seconds=10.0,
        players_timeout_seconds=10.0,
        started_at=datetime(2026, 5, 11, 9, 0, 0, tzinfo=UTC),
        completed_at=datetime(2026, 5, 11, 9, 0, 30, tzinfo=UTC),
        ring=[first, second],
        attempts=attempts,
        pending_skip_counts={"a-1": 0, "b-1": 2},
    )

    assert summary.avg_latency_ms == 100.0
    assert summary.max_latency_ms == 100.0
    assert summary.timeout_attempts == 1
    assert summary.info_timeout_attempts == 1
    assert summary.players_timeout_attempts == 0
    assert summary.pending_skip_count == 2
    assert summary.per_server[0].pending_skips in {0, 2}


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
        verify_a2s_scheduler.A2SStreamAsync,
        "create",
        _fake_create,
    )
    monkeypatch.setattr(
        verify_a2s_scheduler,
        "request_async_impl",
        _fake_request_async_impl,
    )

    with pytest.raises(TimeoutError, match="boom"):
        await verify_a2s_scheduler.request_a2s_protocol(
            address=("127.0.0.1", 27015),
            timeout=5.0,
            encoding="utf-8",
            protocol=object,
        )

    assert transport.close_calls == 1
    assert isinstance(conn.transport, verify_a2s_scheduler._ClosedTransport)


@pytest.mark.asyncio
async def test_query_server_a2s_only_calls_players_when_info_has_players(monkeypatch) -> None:
    class _Info:
        player_count = 0
        map_name = "kz_map"

    calls: list[type[object]] = []

    async def _fake_request_a2s_protocol(
        *,
        address: tuple[str, int],
        timeout: float,
        encoding: str,
        protocol: type[object],
    ) -> object:
        del address, timeout, encoding
        calls.append(protocol)
        return _Info()

    monkeypatch.setattr(
        verify_a2s_scheduler,
        "request_a2s_protocol",
        _fake_request_a2s_protocol,
    )

    result = await verify_a2s_scheduler.query_server_a2s(
        ip="127.0.0.1",
        port=27015,
        timeout=5.0,
        players_timeout=5.0,
    )

    assert result.players_queried is False
    assert calls == [verify_a2s_scheduler.InfoProtocol]


@pytest.mark.asyncio
async def test_run_scheduler_benchmark_skips_pending_targets() -> None:
    target = _target(host="127.0.0.1", port=27015, stable_id="server-1")
    release = asyncio.Event()
    launches = 0
    concurrent = 0
    max_concurrent = 0

    async def _fake_query(
        *,
        ip: str,
        port: int,
        timeout: float,
        players_timeout: float,
    ) -> verify_a2s_scheduler.ProbeQueryResult:
        nonlocal launches, concurrent, max_concurrent
        del ip, port, timeout, players_timeout
        launches += 1
        concurrent += 1
        max_concurrent = max(max_concurrent, concurrent)
        try:
            await release.wait()
            return verify_a2s_scheduler.ProbeQueryResult(
                map_name="kz_test",
                player_count=0,
                info_elapsed_ms=50.0,
                players_elapsed_ms=None,
                players_queried=False,
                players_returned=None,
            )
        finally:
            concurrent -= 1

    async def _release_later() -> None:
        await asyncio.sleep(0.04)
        release.set()

    releaser = asyncio.create_task(_release_later())
    try:
        summary = await verify_a2s_scheduler.run_scheduler_benchmark(
            api_url="https://example.com",
            targets=[target],
            duration_seconds=1,
            interval_seconds=0.02,
            timeout_seconds=5.0,
            players_timeout_seconds=5.0,
            query_fn=_fake_query,
            progress_message=None,
        )
    finally:
        await releaser

    assert max_concurrent == 1
    assert summary.pending_skip_count >= 1
    assert summary.successful_attempts >= 1
    assert launches >= 1


@pytest.mark.asyncio
async def test_run_scheduler_command_writes_json(tmp_path) -> None:
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
                "host": "10.0.0.2",
                "port": 27016,
                "hostname": "Two",
                "country": "DE",
                "group_name": "Group 2",
                "group_custom_id": "group-2",
                "server_id": "two",
                "is_online": True,
            },
        ]
    }
    console_output = io.StringIO()
    console = Console(file=console_output, force_terminal=False, color_system=None)
    output_path = tmp_path / "scheduler.json"

    async def _fake_fetch_targets(
        api_url: str,
    ) -> list[verify_a2s_scheduler.SchedulerTarget]:
        assert api_url == "https://example.com/public-servers"
        return verify_a2s_scheduler.parse_public_server_payload(payload)

    async def _fake_query(
        *,
        ip: str,
        port: int,
        timeout: float,
        players_timeout: float,
    ) -> verify_a2s_scheduler.ProbeQueryResult:
        del ip, port, timeout, players_timeout
        return verify_a2s_scheduler.ProbeQueryResult(
            map_name="kz_test",
            player_count=0,
            info_elapsed_ms=25.0,
            players_elapsed_ms=None,
            players_queried=False,
            players_returned=None,
        )

    summary = await verify_a2s_scheduler.run_scheduler_command(
        api_url="https://example.com/public-servers",
        duration_seconds=1,
        interval_seconds=2.0,
        timeout_seconds=10.0,
        players_timeout_seconds=10.0,
        output_json=output_path,
        limit_servers=None,
        verbose_ring=False,
        console=console,
        query_fn=_fake_query,
        fetch_targets_fn=_fake_fetch_targets,
    )

    assert summary.target_count == 2
    assert summary.total_launches >= 1
    output_payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert output_payload["target_count"] == 2
    assert "pending_skip_counts" in output_payload
    output_text = console_output.getvalue()
    assert "Scheduler configured" in output_text
    assert "tick spacing" in output_text
    assert "Cursor-Scheduled A2S Verification Summary" in output_text
