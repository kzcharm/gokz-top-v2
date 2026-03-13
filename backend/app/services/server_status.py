from __future__ import annotations

import asyncio
import ipaddress
import socket
import struct
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
import psycopg
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.core.config import settings
from app.core.db import async_session_maker
from app.models import ServerStatusPut

SERVER_PLUGIN_FRESH_SECONDS = 5
SERVER_A2S_POLL_SECONDS = 10
SERVER_A2S_FAILURES_BEFORE_OFFLINE = 3
SERVER_A2S_QUERY_TIMEOUT_SECONDS = 2.0
SERVER_DISCOVERY_INTERVAL_SECONDS = 3600
SERVER_HEARTBEAT_RETENTION_DAYS = 30
SERVER_HEARTBEAT_FUTURE_PARTITIONS_DAYS = 7
STEAM_SERVER_LIST_URL = (
    "https://api.steampowered.com/IGameServersService/GetServerList/v1/"
)
SUPPORTED_KZ_MAP_PREFIXES = (
    "kz_",
    "bkz_",
    "vnl_",
    "skz_",
    "xc_",
    "kzpro_",
)
STEAM_SERVER_LIST_REGIONS = tuple(range(8))
STEAM_SERVER_LIST_TIMEOUT_SECONDS = 10.0
SERVER_STATUS_COLLECTOR_LOCK_ID = 4_465_480
A2S_PACKET_PREFIX = b"\xff\xff\xff\xff"
A2S_INFO_REQUEST = A2S_PACKET_PREFIX + b"TSource Engine Query\x00"
A2S_PLAYER_REQUEST_PREFIX = A2S_PACKET_PREFIX + b"U"
A2S_CHALLENGE_REQUEST = b"\xff\xff\xff\xff"
_server_a2s_failures: dict[Any, int] = {}
_server_a2s_in_flight_until: dict[Any, datetime] = {}


@dataclass(slots=True)
class ServerDiscoveryCycleResult:
    started_at: datetime
    completed_at: datetime
    regions_scanned: int
    candidate_count: int
    upserted_count: int


@dataclass(slots=True, frozen=True)
class SteamServerListCandidate:
    ip: str
    port: int
    hostname: str
    map_name: str
    player_count: int
    max_players: int


class ServerQueryError(RuntimeError):
    pass


@dataclass(slots=True)
class A2SInfoResult:
    hostname: str
    map_name: str
    player_count: int
    max_players: int
    players: list[dict[str, Any]]
    observed_at: datetime
    game_directory: str | None = None
    game_name: str | None = None
    app_id: int | None = None


def is_supported_kz_map_name(map_name: str) -> bool:
    normalized_map_name = map_name.strip().casefold()
    return normalized_map_name.startswith(SUPPORTED_KZ_MAP_PREFIXES)


def validate_server_addition_info(result: A2SInfoResult) -> None:
    game_directory = result.game_directory.strip() if result.game_directory else ""
    game_name = result.game_name.strip() if result.game_name else ""
    normalized_game_name = game_name.casefold()
    is_cs_game = game_directory.casefold() == "csgo" or normalized_game_name in {
        "counter-strike 2",
        "counter-strike: global offensive",
        "counter-strike",
    }
    if not is_cs_game:
        observed_game = game_name or game_directory or "unknown"
        raise ServerQueryError(
            f"Server is running game '{observed_game}', expected Counter-Strike"
        )

    if not is_supported_kz_map_name(result.map_name):
        allowed_prefixes = ", ".join(f"{prefix}*" for prefix in SUPPORTED_KZ_MAP_PREFIXES)
        raise ServerQueryError(
            f"Server is running map '{result.map_name}', expected one of {allowed_prefixes}"
        )


def _read_cstring(payload: bytes, offset: int) -> tuple[str, int]:
    end = payload.find(b"\x00", offset)
    if end == -1:
        raise ServerQueryError("Invalid A2S response string encoding")
    return payload[offset:end].decode("utf-8", errors="replace"), end + 1


def _read_int32_le(payload: bytes, offset: int) -> tuple[int, int]:
    if len(payload) < offset + 4:
        raise ServerQueryError("Incomplete A2S int32 payload")
    return int.from_bytes(payload[offset : offset + 4], "little", signed=True), (
        offset + 4
    )


def _read_float32_le(payload: bytes, offset: int) -> tuple[float, int]:
    if len(payload) < offset + 4:
        raise ServerQueryError("Incomplete A2S float payload")
    return struct.unpack_from("<f", payload, offset)[0], offset + 4


def _recv_a2s_packet(sock: socket.socket) -> bytes:
    response, _ = sock.recvfrom(4096)
    if len(response) < 5 or response[:4] != A2S_PACKET_PREFIX:
        raise ServerQueryError("Invalid A2S response header")
    return response


def _send_a2s_request(
    sock: socket.socket,
    *,
    address: tuple[str, int],
    request: bytes,
    response_label: str,
    expected_response_type: int,
    challenged_request_builder: Callable[[bytes], bytes],
) -> bytes:
    sock.sendto(request, address)
    response = _recv_a2s_packet(sock)
    response_type = response[4]

    # Some servers challenge the initial request before returning the payload.
    for _ in range(2):
        if response_type != 0x41:
            break
        challenge = response[5:9]
        if len(challenge) != 4:
            raise ServerQueryError(f"Invalid {response_label} challenge response")
        sock.sendto(challenged_request_builder(challenge), address)
        response = _recv_a2s_packet(sock)
        response_type = response[4]

    if response_type != expected_response_type:
        raise ServerQueryError(f"Unsupported {response_label} response type")
    return response


def _parse_a2s_info_response(
    response: bytes,
) -> tuple[str, str, str, str, int, int, int]:
    offset = 6
    hostname, offset = _read_cstring(response, offset)
    map_name, offset = _read_cstring(response, offset)
    game_directory, offset = _read_cstring(response, offset)
    game_name, offset = _read_cstring(response, offset)

    if len(response) < offset + 4:
        raise ServerQueryError("Incomplete A2S info payload")
    app_id = int.from_bytes(response[offset : offset + 2], "little", signed=False)
    offset += 2
    player_count = response[offset]
    max_players = response[offset + 1]
    return (
        hostname,
        map_name,
        game_directory,
        game_name,
        app_id,
        player_count,
        max_players,
    )


def _query_a2s_players_sync(
    sock: socket.socket,
    *,
    address: tuple[str, int],
) -> list[dict[str, Any]]:
    response = _send_a2s_request(
        sock,
        address=address,
        request=A2S_PLAYER_REQUEST_PREFIX + A2S_CHALLENGE_REQUEST,
        response_label="A2S player",
        expected_response_type=0x44,
        challenged_request_builder=lambda challenge: A2S_PLAYER_REQUEST_PREFIX
        + challenge,
    )
    if len(response) < 6:
        raise ServerQueryError("Incomplete A2S player payload")

    declared_player_count = response[5]
    offset = 6
    players: list[dict[str, Any]] = []

    for _ in range(declared_player_count):
        if len(response) <= offset:
            raise ServerQueryError("Incomplete A2S player payload")
        player_index = response[offset]
        offset += 1
        name, offset = _read_cstring(response, offset)
        score, offset = _read_int32_le(response, offset)
        duration_seconds, offset = _read_float32_le(response, offset)
        players.append(
            {
                "index": player_index,
                "name": name,
                "score": score,
                "duration_seconds": duration_seconds,
            }
        )

    return players


def _create_udp_socket() -> socket.socket:
    return socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


def _query_a2s_info_sync(ip: str, port: int, timeout: float) -> A2SInfoResult:
    address = (ip, port)

    try:
        with _create_udp_socket() as sock:
            sock.settimeout(timeout)
            info_response = _send_a2s_request(
                sock,
                address=address,
                request=A2S_INFO_REQUEST,
                response_label="A2S info",
                expected_response_type=0x49,
                challenged_request_builder=lambda challenge: A2S_INFO_REQUEST
                + challenge,
            )
            (
                hostname,
                map_name,
                game_directory,
                game_name,
                app_id,
                player_count,
                max_players,
            ) = _parse_a2s_info_response(info_response)
            try:
                players = _query_a2s_players_sync(sock, address=address)
            except ServerQueryError:
                players = []

            return A2SInfoResult(
                hostname=hostname,
                map_name=map_name,
                game_directory=game_directory,
                game_name=game_name,
                app_id=app_id,
                player_count=player_count,
                max_players=max_players,
                players=players,
                observed_at=datetime.now(UTC),
            )
    except OSError as exc:
        raise ServerQueryError(f"A2S query failed for {ip}:{port}") from exc


async def query_server_a2s_info(
    *,
    ip: str,
    port: int,
    timeout: float = SERVER_A2S_QUERY_TIMEOUT_SECONDS,
) -> A2SInfoResult:
    try:
        return await asyncio.to_thread(_query_a2s_info_sync, ip, port, timeout)
    except OSError as exc:
        raise ServerQueryError(f"A2S query failed for {ip}:{port}") from exc


def _parse_server_addr(addr: str) -> tuple[str, int] | None:
    host, separator, port_str = addr.rpartition(":")
    if separator == "":
        return None
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    try:
        parsed_ip = ipaddress.ip_address(host)
        port = int(port_str)
    except ValueError:
        return None
    if parsed_ip.version != 4 or not 1 <= port <= 65535:
        return None
    return str(parsed_ip), port


def _extract_server_list_candidates(
    payloads: list[dict[str, Any]],
) -> list[SteamServerListCandidate]:
    deduped: list[SteamServerListCandidate] = []
    seen: set[tuple[str, int]] = set()

    for payload in payloads:
        response_payload = payload.get("response")
        if not isinstance(response_payload, dict):
            continue
        servers_payload = response_payload.get("servers")
        if not isinstance(servers_payload, list):
            continue

        for server_payload in servers_payload:
            if not isinstance(server_payload, dict):
                continue
            addr = server_payload.get("addr")
            if not isinstance(addr, str):
                continue
            endpoint = _parse_server_addr(addr)
            if endpoint is None or endpoint in seen:
                continue
            hostname = server_payload.get("name")
            map_name = server_payload.get("map")
            player_count = server_payload.get("players")
            max_players = server_payload.get("max_players")
            if not isinstance(hostname, str) or not hostname.strip():
                continue
            if not isinstance(map_name, str) or not map_name.strip():
                continue
            if not isinstance(player_count, int) or player_count < 0:
                continue
            if not isinstance(max_players, int) or max_players < 0:
                continue
            seen.add(endpoint)
            deduped.append(
                SteamServerListCandidate(
                    ip=endpoint[0],
                    port=endpoint[1],
                    hostname=hostname.strip(),
                    map_name=map_name.strip(),
                    player_count=player_count,
                    max_players=max_players,
                )
            )

    return deduped


async def query_steam_server_list_candidates() -> list[SteamServerListCandidate]:
    if not settings.STEAM_API_KEY:
        raise ServerQueryError("STEAM_API_KEY is not configured")

    try:
        async with httpx.AsyncClient(
            timeout=STEAM_SERVER_LIST_TIMEOUT_SECONDS
        ) as client:
            tasks = [
                client.get(
                    STEAM_SERVER_LIST_URL,
                    params={
                        "key": settings.STEAM_API_KEY,
                        "filter": (
                            f"\\appid\\{settings.STEAM_SERVER_LIST_APP_ID}"
                            f"\\region\\{region}"
                        ),
                        "limit": settings.STEAM_SERVER_LIST_LIMIT,
                    },
                )
                for region in STEAM_SERVER_LIST_REGIONS
            ]
            responses = await asyncio.gather(*tasks)
    except httpx.HTTPError as exc:
        raise ServerQueryError("Steam server list query failed") from exc

    payloads: list[dict[str, Any]] = []
    for response in responses:
        try:
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ServerQueryError("Steam server list query failed") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise ServerQueryError("Steam server list returned invalid JSON") from exc

        if not isinstance(payload, dict):
            raise ServerQueryError("Steam server list returned invalid payload")
        payloads.append(payload)

    return _extract_server_list_candidates(payloads)


def _partition_name(partition_date: date) -> str:
    return f"server_heartbeat_raw_p_{partition_date:%Y%m%d}"


async def ensure_server_heartbeat_partitions(
    *,
    session: AsyncSession,
    start_date: date,
    end_date: date,
) -> None:
    partition_date = start_date
    while partition_date <= end_date:
        partition_name = _partition_name(partition_date)
        next_date = partition_date + timedelta(days=1)
        await session.execute(
            text(
                f'CREATE TABLE IF NOT EXISTS "{partition_name}" '
                "PARTITION OF server_heartbeat_raw "
                f"FOR VALUES FROM ('{partition_date.isoformat()}') "
                f"TO ('{next_date.isoformat()}')"
            )
        )
        partition_date = next_date


async def drop_expired_server_heartbeat_partitions(
    *,
    session: AsyncSession,
    reference_date: date,
) -> None:
    keep_from = reference_date - timedelta(days=SERVER_HEARTBEAT_RETENTION_DAYS - 1)
    rows = list(
        (
            await session.execute(
                text(
                    "SELECT tablename "
                    "FROM pg_tables "
                    "WHERE schemaname = current_schema() "
                    "AND tablename LIKE 'server_heartbeat_raw_p_%'"
                )
            )
        ).all()
    )
    keep_from_name = _partition_name(keep_from)
    for row in rows:
        table_name = row[0]
        if table_name < keep_from_name:
            await session.execute(text(f'DROP TABLE IF EXISTS "{table_name}"'))


async def maintain_server_heartbeat_partitions(*, session: AsyncSession) -> None:
    today = datetime.now(UTC).date()
    await ensure_server_heartbeat_partitions(
        session=session,
        start_date=today - timedelta(days=SERVER_HEARTBEAT_RETENTION_DAYS),
        end_date=today + timedelta(days=SERVER_HEARTBEAT_FUTURE_PARTITIONS_DAYS),
    )
    await drop_expired_server_heartbeat_partitions(
        session=session, reference_date=today
    )
    await session.commit()


async def run_server_discovery_cycle() -> ServerDiscoveryCycleResult:
    started_at = datetime.now(UTC)
    candidates = await query_steam_server_list_candidates()
    kz_candidates = [
        candidate
        for candidate in candidates
        if is_supported_kz_map_name(candidate.map_name)
    ]

    async with async_session_maker() as session:
        await maintain_server_heartbeat_partitions(session=session)
        for candidate in kz_candidates:
            await crud.upsert_discovered_server(
                session=session,
                ip=candidate.ip,
                port=candidate.port,
                hostname=candidate.hostname,
                map_name=candidate.map_name,
                player_count=candidate.player_count,
                max_players=candidate.max_players,
                players=[],
                observed_at=started_at,
                commit=False,
            )
        await session.commit()

    return ServerDiscoveryCycleResult(
        started_at=started_at,
        completed_at=datetime.now(UTC),
        regions_scanned=len(STEAM_SERVER_LIST_REGIONS),
        candidate_count=len(candidates),
        upserted_count=len(kz_candidates),
    )


def _is_server_a2s_query_in_flight(*, server_id: Any, now: datetime) -> bool:
    in_flight_until = _server_a2s_in_flight_until.get(server_id)
    if in_flight_until is None:
        return False
    if in_flight_until <= now:
        _server_a2s_in_flight_until.pop(server_id, None)
        return False
    return True


def _mark_server_a2s_query_started(*, server_id: Any, now: datetime) -> None:
    _server_a2s_in_flight_until[server_id] = now + timedelta(
        seconds=SERVER_A2S_QUERY_TIMEOUT_SECONDS
    )


def _mark_server_a2s_query_finished(*, server_id: Any) -> None:
    _server_a2s_in_flight_until.pop(server_id, None)


def _reset_server_a2s_failures(*, server_id: Any) -> None:
    _server_a2s_failures.pop(server_id, None)


def _increment_server_a2s_failures(*, server_id: Any) -> int:
    next_failures = _server_a2s_failures.get(server_id, 0) + 1
    _server_a2s_failures[server_id] = next_failures
    return next_failures


async def run_server_a2s_refresh_cycle() -> None:
    now = datetime.now(UTC)
    async with async_session_maker() as session:
        servers = await crud.read_servers_due_for_a2s_poll(
            session=session,
            now=now,
            plugin_stale_after_seconds=SERVER_PLUGIN_FRESH_SECONDS,
            a2s_poll_after_seconds=SERVER_A2S_POLL_SECONDS,
        )

    semaphore = asyncio.Semaphore(20)
    eligible_servers = []
    for server in servers:
        status = server.live_status
        if (
            status is not None
            and status.last_successful_seen_at is not None
            and (
                status.last_a2s_seen_at is None
                or status.last_successful_seen_at >= status.last_a2s_seen_at
            )
        ):
            _reset_server_a2s_failures(server_id=server.id)

        if _is_server_a2s_query_in_flight(server_id=server.id, now=now):
            continue

        _mark_server_a2s_query_started(server_id=server.id, now=now)
        eligible_servers.append(server)

    async def _probe(
        server_id: Any, ip: str, port: int
    ) -> tuple[Any, A2SInfoResult | None]:
        try:
            async with semaphore:
                try:
                    result = await query_server_a2s_info(ip=ip, port=port)
                except ServerQueryError:
                    return server_id, None
            return server_id, result
        finally:
            _mark_server_a2s_query_finished(server_id=server_id)

    server_refs = [(server.id, server.ip, server.port) for server in eligible_servers]
    results = await asyncio.gather(
        *[_probe(server_id, ip, port) for server_id, ip, port in server_refs],
        return_exceptions=False,
    )

    for server_id, info in results:
        async with async_session_maker() as session:
            server = await crud.get_server_by_id(session=session, server_id=server_id)
            if server is None:
                _reset_server_a2s_failures(server_id=server_id)
                continue
            if info is None:
                failures = _increment_server_a2s_failures(server_id=server_id)
                await crud.record_a2s_failure(
                    session=session,
                    server=server,
                    observed_at=datetime.now(UTC),
                    mark_offline=failures >= SERVER_A2S_FAILURES_BEFORE_OFFLINE,
                )
                continue
            _reset_server_a2s_failures(server_id=server_id)
            await crud.record_a2s_success(
                session=session,
                server=server,
                observed_at=info.observed_at,
                hostname=info.hostname,
                map_name=info.map_name,
                player_count=info.player_count,
                max_players=info.max_players,
                players=info.players,
            )


async def run_server_status_collector() -> None:
    last_discovery_at = datetime.min.replace(tzinfo=UTC)
    while True:
        now = datetime.now(UTC)
        if (
            now - last_discovery_at
        ).total_seconds() >= SERVER_DISCOVERY_INTERVAL_SECONDS:
            try:
                await run_server_discovery_cycle()
            except Exception:
                pass
            last_discovery_at = now

        try:
            await run_server_a2s_refresh_cycle()
        except Exception:
            pass

        await asyncio.sleep(1)


def _psycopg_database_uri() -> str:
    return str(settings.SQLALCHEMY_DATABASE_URI).replace(
        "postgresql+psycopg", "postgresql", 1
    )


async def run_server_status_collector_in_app() -> None:
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
                    await run_server_status_collector()
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


async def put_server_status_from_plugin(
    *,
    api_key: str,
    payload: ServerStatusPut,
) -> None:
    async with async_session_maker() as session:
        group = await crud.get_server_group_by_api_key(session=session, api_key=api_key)
        if group is None:
            raise ServerQueryError("Invalid server group API key")

        server = await crud.get_server_by_endpoint(
            session=session,
            ip=payload.ip,
            port=payload.port,
        )
        if server is None:
            raise ServerQueryError("Server not found")
        if not server.enabled:
            raise ServerQueryError("Server is disabled")
        if server.group_id != group.id:
            raise ServerQueryError("Server does not belong to this group")

        await crud.record_plugin_heartbeat(
            session=session, server=server, payload=payload
        )


def main() -> None:
    asyncio.run(run_server_status_collector())


if __name__ == "__main__":
    main()
