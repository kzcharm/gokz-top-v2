import asyncio
import struct
from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.crud import server as server_crud
from app.models import Server, ServerSource, ServerStatusPut
from app.services import server_status
from app.services.geoip import GeoIPLocation
from app.services.server_status import (
    A2SInfoResult,
    ServerQueryError,
    SteamServerListCandidate,
)
from tests.utils.server import create_server

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def reset_server_status_runtime_state() -> Generator[None]:
    server_status._server_a2s_failures.clear()
    server_status._server_a2s_in_flight_until.clear()
    yield
    server_status._server_a2s_failures.clear()
    server_status._server_a2s_in_flight_until.clear()


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


class _FakeAdvisoryLockCursor:
    def __init__(self, connection: _FakeAdvisoryLockConnection) -> None:
        self._connection = connection

    async def __aenter__(self) -> _FakeAdvisoryLockCursor:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def execute(self, query: str, params: tuple[int] | None = None) -> None:
        self._connection.executed.append((query, params))

    async def fetchone(self) -> tuple[bool]:
        return (self._connection.lock_acquired,)


class _FakeAdvisoryLockConnection:
    def __init__(self, *, lock_acquired: bool) -> None:
        self.lock_acquired = lock_acquired
        self.executed: list[tuple[str, tuple[int] | None]] = []

    async def __aenter__(self) -> _FakeAdvisoryLockConnection:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    def cursor(self) -> _FakeAdvisoryLockCursor:
        return _FakeAdvisoryLockCursor(self)


class _FakeA2SSocket:
    def __init__(self, responses: list[bytes]) -> None:
        self._responses = list(responses)
        self.sent_packets: list[tuple[bytes, tuple[str, int]]] = []
        self.timeout: float | None = None

    def __enter__(self) -> _FakeA2SSocket:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def settimeout(self, timeout: float) -> None:
        self.timeout = timeout

    def sendto(self, payload: bytes, address: tuple[str, int]) -> None:
        self.sent_packets.append((payload, address))

    def recvfrom(self, size: int) -> tuple[bytes, tuple[str, int]]:
        del size
        if not self._responses:
            raise AssertionError("No fake A2S responses remaining")
        return self._responses.pop(0), ("127.0.0.1", 27015)


def _build_a2s_player_entry(
    *,
    index: int,
    name: str,
    score: int,
    duration_seconds: float,
) -> bytes:
    return (
        bytes([index])
        + name.encode("utf-8")
        + b"\x00"
        + score.to_bytes(4, "little", signed=True)
        + struct.pack("<f", duration_seconds)
    )


async def test_read_servers_due_for_a2s_poll_skips_fresh_plugin_heartbeats(
    db: AsyncSession,
) -> None:
    fresh_server = await create_server(db)
    stale_server = await create_server(db)
    now = datetime.now(UTC)

    fresh_server = await crud.record_plugin_heartbeat(
        session=db,
        server=fresh_server,
        payload=ServerStatusPut(
            ip=fresh_server.ip,
            port=fresh_server.port,
            observed_at=now,
            hostname="Fresh Host",
            map="kz_fresh",
            player_count=5,
            max_players=16,
            players=[],
        ),
    )
    stale_server = await crud.record_plugin_heartbeat(
        session=db,
        server=stale_server,
        payload=ServerStatusPut(
            ip=stale_server.ip,
            port=stale_server.port,
            observed_at=now - timedelta(seconds=10),
            hostname="Stale Host",
            map="kz_stale",
            player_count=5,
            max_players=16,
            players=[],
        ),
    )
    assert stale_server.live_status is not None
    stale_server.live_status.last_a2s_seen_at = now - timedelta(seconds=10)
    db.add(stale_server.live_status)
    await db.commit()

    due_servers = await crud.read_servers_due_for_a2s_poll(
        session=db,
        now=now,
        plugin_stale_after_seconds=5,
        a2s_poll_after_seconds=5,
    )

    due_server_ids = {server.id for server in due_servers}
    assert fresh_server.id not in due_server_ids
    assert stale_server.id in due_server_ids


async def test_run_server_discovery_cycle_only_tracks_supported_kz_prefixes(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_query_steam_server_list_candidates() -> list[
        SteamServerListCandidate
    ]:
        return [
            SteamServerListCandidate(
                ip="127.10.0.1",
                port=27015,
                hostname="KZ Server",
                map_name="kz_discovered",
                player_count=1,
                max_players=20,
            ),
            SteamServerListCandidate(
                ip="127.10.0.2",
                port=27016,
                hostname="BKZ Server",
                map_name="bkz_beta",
                player_count=1,
                max_players=20,
            ),
            SteamServerListCandidate(
                ip="127.10.0.3",
                port=27017,
                hostname="Other Server",
                map_name="de_dust2",
                player_count=1,
                max_players=20,
            ),
        ]

    async def _unexpected_query_server_a2s_info(*, ip: str, port: int) -> A2SInfoResult:
        del ip, port
        raise AssertionError("Discovery should not A2S query Steam server-list results")

    monkeypatch.setattr(
        server_status,
        "query_steam_server_list_candidates",
        _fake_query_steam_server_list_candidates,
    )
    monkeypatch.setattr(
        server_status,
        "query_server_a2s_info",
        _unexpected_query_server_a2s_info,
    )
    monkeypatch.setattr(
        server_crud,
        "lookup_geoip_city",
        lambda ip: GeoIPLocation(country_code="SE", city_name="Stockholm"),
    )
    monkeypatch.setattr(
        server_status,
        "async_session_maker",
        _StaticSessionFactory(db),
    )

    result = await server_status.run_server_discovery_cycle()

    statement = select(Server).where(
        col(Server.source) == ServerSource.STEAM_MASTER,
        col(Server.ip).in_(("127.10.0.1", "127.10.0.2")),
    )
    servers = list((await db.exec(statement)).all())
    assert result.regions_scanned == 8
    assert result.candidate_count == 3
    assert result.upserted_count == 2
    assert len(servers) == 2
    assert {server.ip for server in servers} == {"127.10.0.1", "127.10.0.2"}
    assert all(server.enabled is True for server in servers)
    assert {server.configured_hostname for server in servers} == {
        "KZ Server",
        "BKZ Server",
    }
    assert all(server.country == "SE" for server in servers)
    assert all(server.city == "Stockholm" for server in servers)


async def test_extract_server_list_candidates_dedupes_and_skips_invalid_rows() -> None:
    payloads = [
        {
            "response": {
                "servers": [
                    {
                        "addr": "127.0.0.1:27015",
                        "name": "KZ One",
                        "map": "kz_alpha",
                        "players": 3,
                        "max_players": 16,
                    },
                    {
                        "addr": "127.0.0.1:27015",
                        "name": "KZ One Duplicate",
                        "map": "kz_alpha",
                        "players": 4,
                        "max_players": 16,
                    },
                    {"addr": "not-an-endpoint"},
                ]
            }
        },
        {
            "response": {
                "servers": [
                    {
                        "addr": "127.0.0.2:27016",
                        "name": "Dust Server",
                        "map": "de_dust2",
                        "players": 0,
                        "max_players": 10,
                    },
                    {"addr": "[2001:db8::1]:27015"},
                ]
            }
        },
    ]

    candidates = server_status._extract_server_list_candidates(payloads)

    assert candidates == [
        SteamServerListCandidate(
            ip="127.0.0.1",
            port=27015,
            hostname="KZ One",
            map_name="kz_alpha",
            player_count=3,
            max_players=16,
        ),
        SteamServerListCandidate(
            ip="127.0.0.2",
            port=27016,
            hostname="Dust Server",
            map_name="de_dust2",
            player_count=0,
            max_players=10,
        ),
    ]


async def test_query_server_a2s_info_wraps_socket_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_query_a2s_info_sync(ip: str, port: int, timeout: float) -> A2SInfoResult:
        del ip, port, timeout
        raise TimeoutError("timed out")

    monkeypatch.setattr(
        server_status,
        "_query_a2s_info_sync",
        _fake_query_a2s_info_sync,
    )

    with pytest.raises(ServerQueryError):
        await server_status.query_server_a2s_info(ip="127.0.0.1", port=27015)


async def test_query_a2s_info_sync_parses_players(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    player_challenge = b"\x12\x34\x56\x78"
    info_response = (
        server_status.A2S_PACKET_PREFIX
        + b"\x49\x11"
        + b"Test Host\x00"
        + b"kz_alpha\x00"
        + b"csgo\x00"
        + b"Counter-Strike 2\x00"
        + (730).to_bytes(2, "little")
        + bytes([2, 16])
    )
    player_challenge_response = (
        server_status.A2S_PACKET_PREFIX + b"\x41" + player_challenge
    )
    player_response = (
        server_status.A2S_PACKET_PREFIX
        + b"\x44"
        + bytes([2])
        + _build_a2s_player_entry(
            index=0,
            name="Alice",
            score=12,
            duration_seconds=45.5,
        )
        + _build_a2s_player_entry(
            index=1,
            name="Bob",
            score=-3,
            duration_seconds=12.25,
        )
    )
    fake_socket = _FakeA2SSocket(
        [info_response, player_challenge_response, player_response]
    )

    monkeypatch.setattr(
        server_status,
        "_create_udp_socket",
        lambda: fake_socket,
    )

    result = server_status._query_a2s_info_sync("127.0.0.1", 27015, 1.5)

    assert fake_socket.timeout == 1.5
    assert fake_socket.sent_packets == [
        (server_status.A2S_INFO_REQUEST, ("127.0.0.1", 27015)),
        (
            server_status.A2S_PLAYER_REQUEST_PREFIX
            + server_status.A2S_CHALLENGE_REQUEST,
            ("127.0.0.1", 27015),
        ),
        (
            server_status.A2S_PLAYER_REQUEST_PREFIX + player_challenge,
            ("127.0.0.1", 27015),
        ),
    ]
    assert result.hostname == "Test Host"
    assert result.map_name == "kz_alpha"
    assert result.game_directory == "csgo"
    assert result.game_name == "Counter-Strike 2"
    assert result.app_id == 730
    assert result.player_count == 2
    assert result.max_players == 16
    assert result.players == [
        {
            "index": 0,
            "name": "Alice",
            "score": 12,
            "duration_seconds": 45.5,
        },
        {
            "index": 1,
            "name": "Bob",
            "score": -3,
            "duration_seconds": 12.25,
        },
    ]


async def test_run_server_a2s_refresh_cycle_updates_stale_players(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = await create_server(db)
    assert server.live_status is not None
    server.live_status.last_a2s_seen_at = datetime.now(UTC) - timedelta(seconds=10)
    server.live_status.players = [{"name": "Old Player"}]
    server.live_status.player_count = 1
    db.add(server.live_status)
    await db.commit()

    async def _fake_query_server_a2s_info(*, ip: str, port: int) -> A2SInfoResult:
        assert ip == server.ip
        assert port == server.port
        return A2SInfoResult(
            hostname="Refreshed Host",
            map_name="kz_refresh",
            player_count=2,
            max_players=16,
            players=[
                {"name": "Player One", "score": 7, "duration_seconds": 33.0},
                {"name": "Player Two", "score": 1, "duration_seconds": 11.0},
            ],
            observed_at=datetime.now(UTC),
        )

    monkeypatch.setattr(
        server_status,
        "query_server_a2s_info",
        _fake_query_server_a2s_info,
    )
    monkeypatch.setattr(
        server_status.crud,
        "read_servers_due_for_a2s_poll",
        lambda **kwargs: asyncio.sleep(0, result=[server]),
    )
    monkeypatch.setattr(
        server_status,
        "async_session_maker",
        _StaticSessionFactory(db),
    )

    await server_status.run_server_a2s_refresh_cycle()

    refreshed = await crud.get_server_by_id(session=db, server_id=server.id)
    assert refreshed is not None
    assert refreshed.live_status is not None
    assert refreshed.live_status.current_hostname == "Refreshed Host"
    assert refreshed.live_status.map == "kz_refresh"
    assert refreshed.live_status.player_count == 2
    assert refreshed.live_status.players == [
        {"name": "Player One", "score": 7, "duration_seconds": 33.0},
        {"name": "Player Two", "score": 1, "duration_seconds": 11.0},
    ]


async def test_run_server_a2s_refresh_cycle_keeps_recent_server_online_on_single_failure(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = await create_server(db, player_count=4, max_players=20)
    assert server.live_status is not None

    previous_success_at = datetime.now(UTC) - timedelta(seconds=10)
    server.live_status.last_successful_seen_at = previous_success_at
    server.live_status.last_a2s_seen_at = previous_success_at - timedelta(seconds=10)
    server.live_status.is_online = True
    server.live_status.players = [{"name": "Player One"}]
    db.add(server.live_status)
    await db.commit()

    async def _failing_query_server_a2s_info(*, ip: str, port: int) -> A2SInfoResult:
        del ip, port
        raise ServerQueryError("temporary timeout")

    monkeypatch.setattr(
        server_status,
        "query_server_a2s_info",
        _failing_query_server_a2s_info,
    )
    monkeypatch.setattr(
        server_status.crud,
        "read_servers_due_for_a2s_poll",
        lambda **kwargs: asyncio.sleep(0, result=[server]),
    )
    monkeypatch.setattr(
        server_status,
        "async_session_maker",
        _StaticSessionFactory(db),
    )

    await server_status.run_server_a2s_refresh_cycle()

    refreshed = await crud.get_server_by_id(session=db, server_id=server.id)
    assert refreshed is not None
    assert refreshed.live_status is not None
    assert refreshed.live_status.is_online is True
    assert refreshed.live_status.player_count == 4
    assert refreshed.live_status.players == [{"name": "Player One"}]
    assert refreshed.live_status.last_successful_seen_at == previous_success_at
    assert refreshed.live_status.last_a2s_seen_at is not None
    assert refreshed.live_status.last_a2s_seen_at > previous_success_at


async def test_run_server_a2s_refresh_cycle_marks_server_offline_after_three_failures(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = await create_server(db, player_count=4, max_players=20)
    assert server.live_status is not None

    previous_success_at = datetime.now(UTC) - timedelta(seconds=10)
    server.live_status.last_successful_seen_at = previous_success_at
    server.live_status.last_a2s_seen_at = previous_success_at - timedelta(seconds=10)
    server.live_status.is_online = True
    server.live_status.players = [{"name": "Player One"}]
    db.add(server.live_status)
    await db.commit()

    async def _failing_query_server_a2s_info(*, ip: str, port: int) -> A2SInfoResult:
        del ip, port
        raise ServerQueryError("server unreachable")

    monkeypatch.setattr(
        server_status,
        "query_server_a2s_info",
        _failing_query_server_a2s_info,
    )
    monkeypatch.setattr(
        server_status.crud,
        "read_servers_due_for_a2s_poll",
        lambda **kwargs: asyncio.sleep(0, result=[server]),
    )
    monkeypatch.setattr(
        server_status,
        "async_session_maker",
        _StaticSessionFactory(db),
    )

    await server_status.run_server_a2s_refresh_cycle()
    first_failure = await crud.get_server_by_id(session=db, server_id=server.id)
    assert first_failure is not None
    assert first_failure.live_status is not None
    assert first_failure.live_status.is_online is True
    assert first_failure.live_status.player_count == 4
    assert first_failure.live_status.players == [{"name": "Player One"}]

    await server_status.run_server_a2s_refresh_cycle()
    second_failure = await crud.get_server_by_id(session=db, server_id=server.id)
    assert second_failure is not None
    assert second_failure.live_status is not None
    assert second_failure.live_status.is_online is True
    assert second_failure.live_status.player_count == 4
    assert second_failure.live_status.players == [{"name": "Player One"}]

    await server_status.run_server_a2s_refresh_cycle()

    refreshed = await crud.get_server_by_id(session=db, server_id=server.id)
    assert refreshed is not None
    assert refreshed.live_status is not None
    assert refreshed.live_status.is_online is False
    assert refreshed.live_status.player_count == 0
    assert refreshed.live_status.players == []
    assert refreshed.live_status.current_hostname == "Test Server"


async def test_run_server_a2s_refresh_cycle_skips_server_with_inflight_query(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = await create_server(db)
    assert server.live_status is not None
    server.live_status.last_a2s_seen_at = datetime.now(UTC) - timedelta(seconds=10)
    db.add(server.live_status)
    await db.commit()

    query_started = asyncio.Event()
    allow_query_to_finish = asyncio.Event()
    query_call_count = 0

    async def _slow_query_server_a2s_info(*, ip: str, port: int) -> A2SInfoResult:
        nonlocal query_call_count
        query_call_count += 1
        assert ip == server.ip
        assert port == server.port
        query_started.set()
        await allow_query_to_finish.wait()
        return A2SInfoResult(
            hostname="Recovered Host",
            map_name="kz_recovered",
            player_count=2,
            max_players=16,
            players=[],
            observed_at=datetime.now(UTC),
        )

    monkeypatch.setattr(
        server_status,
        "query_server_a2s_info",
        _slow_query_server_a2s_info,
    )
    monkeypatch.setattr(
        server_status.crud,
        "read_servers_due_for_a2s_poll",
        lambda **kwargs: asyncio.sleep(0, result=[server]),
    )
    monkeypatch.setattr(
        server_status,
        "async_session_maker",
        _StaticSessionFactory(db),
    )

    first_cycle = asyncio.create_task(server_status.run_server_a2s_refresh_cycle())
    await query_started.wait()

    await server_status.run_server_a2s_refresh_cycle()
    assert query_call_count == 1

    allow_query_to_finish.set()
    await first_cycle


async def test_run_server_status_collector_in_app_uses_advisory_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_connection = _FakeAdvisoryLockConnection(lock_acquired=True)
    collector_started = False

    async def _fake_connect(dsn: str, autocommit: bool) -> _FakeAdvisoryLockConnection:
        del dsn, autocommit
        return fake_connection

    async def _fake_run_server_status_collector() -> None:
        nonlocal collector_started
        collector_started = True
        raise asyncio.CancelledError

    monkeypatch.setattr(
        server_status.psycopg.AsyncConnection,
        "connect",
        _fake_connect,
    )
    monkeypatch.setattr(
        server_status,
        "run_server_status_collector",
        _fake_run_server_status_collector,
    )

    with pytest.raises(asyncio.CancelledError):
        await server_status.run_server_status_collector_in_app()

    assert collector_started is True
    assert fake_connection.executed == [
        (
            "SELECT pg_try_advisory_lock(%s)",
            (server_status.SERVER_STATUS_COLLECTOR_LOCK_ID,),
        ),
        (
            "SELECT pg_advisory_unlock(%s)",
            (server_status.SERVER_STATUS_COLLECTOR_LOCK_ID,),
        ),
    ]


async def test_run_server_status_collector_in_app_skips_without_advisory_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_connection = _FakeAdvisoryLockConnection(lock_acquired=False)
    collector_started = False

    async def _fake_connect(dsn: str, autocommit: bool) -> _FakeAdvisoryLockConnection:
        del dsn, autocommit
        return fake_connection

    async def _fake_run_server_status_collector() -> None:
        nonlocal collector_started
        collector_started = True

    async def _cancel_sleep(delay: float) -> None:
        del delay
        raise asyncio.CancelledError

    monkeypatch.setattr(
        server_status.psycopg.AsyncConnection,
        "connect",
        _fake_connect,
    )
    monkeypatch.setattr(
        server_status,
        "run_server_status_collector",
        _fake_run_server_status_collector,
    )
    monkeypatch.setattr(server_status.asyncio, "sleep", _cancel_sleep)

    with pytest.raises(asyncio.CancelledError):
        await server_status.run_server_status_collector_in_app()

    assert collector_started is False
    assert fake_connection.executed == [
        (
            "SELECT pg_try_advisory_lock(%s)",
            (server_status.SERVER_STATUS_COLLECTOR_LOCK_ID,),
        ),
    ]
