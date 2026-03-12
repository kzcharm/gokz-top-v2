import asyncio
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


async def test_run_server_discovery_cycle_only_tracks_kz_servers(
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
        col(Server.ip) == "127.10.0.1",
        col(Server.port) == 27015,
    )
    servers = list((await db.exec(statement)).all())
    assert result.regions_scanned == 8
    assert result.candidate_count == 2
    assert result.upserted_count == 1
    assert len(servers) == 1
    assert servers[0].ip == "127.10.0.1"
    assert servers[0].enabled is True
    assert servers[0].configured_hostname == "KZ Server"
    assert servers[0].country == "SE"
    assert servers[0].city == "Stockholm"


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
