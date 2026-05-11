from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from a2s.a2s_async import (  # type: ignore[import-untyped]
    A2SStreamAsync,
    request_async_impl,
)
from a2s.info import InfoProtocol  # type: ignore[import-untyped]
from a2s.players import PlayersProtocol  # type: ignore[import-untyped]

SUPPORTED_KZ_MAP_PREFIXES = (
    "kz_",
    "bkz_",
    "vnl_",
    "skz_",
    "xc_",
    "kzpro_",
)


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


class _ClosedTransport:
    def close(self) -> None:
        return


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


def is_supported_kz_map_name(map_name: str) -> bool:
    normalized_map_name = map_name.strip().casefold()
    return normalized_map_name.startswith(SUPPORTED_KZ_MAP_PREFIXES)


def validate_server_addition_info(result: A2SInfoResult) -> None:
    game_directory = result.game_directory.strip() if result.game_directory else ""
    game_name = result.game_name.strip() if result.game_name else ""
    normalized_game_name = game_name.casefold()
    if normalized_game_name == "counter-strike 2":
        raise ServerQueryError(
            "Server is running game 'Counter-Strike 2', expected Counter-Strike: Global Offensive"
        )

    is_supported_game = game_directory.casefold() == "csgo" or normalized_game_name in {
        "counter-strike: global offensive",
        "counter-strike",
    }
    if not is_supported_game:
        observed_game = game_name or game_directory or "unknown"
        raise ServerQueryError(
            f"Server is running game '{observed_game}', expected Counter-Strike: Global Offensive"
        )

    if not is_supported_kz_map_name(result.map_name):
        allowed_prefixes = ", ".join(f"{prefix}*" for prefix in SUPPORTED_KZ_MAP_PREFIXES)
        raise ServerQueryError(
            f"Server is running map '{result.map_name}', expected one of {allowed_prefixes}"
        )


def _players_to_public(players: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "index": int(player.index),
            "name": str(player.name),
            "score": int(player.score),
            "duration_seconds": float(player.duration),
        }
        for player in players
    ]


async def query_server_a2s_info(
    *,
    ip: str,
    port: int,
    timeout: float = 10.0,
    players_timeout: float | None = None,
) -> A2SInfoResult:
    address = (ip, port)
    effective_players_timeout = players_timeout if players_timeout is not None else timeout
    try:
        info = await request_a2s_protocol(
            address=address,
            timeout=timeout,
            encoding="utf-8",
            protocol=InfoProtocol,
        )
    except Exception as exc:
        raise ServerQueryError(f"A2S query failed for {ip}:{port}") from exc

    players: list[dict[str, Any]] = []
    player_count = int(info.player_count)
    if player_count > 0:
        try:
            raw_players = await request_a2s_protocol(
                address=address,
                timeout=effective_players_timeout,
                encoding="utf-8",
                protocol=PlayersProtocol,
            )
        except Exception as exc:
            raise ServerQueryError(f"A2S query failed for {ip}:{port}") from exc
        players = _players_to_public(raw_players)

    observed_at = datetime.now(UTC)
    return A2SInfoResult(
        hostname=str(info.server_name),
        map_name=str(info.map_name),
        player_count=player_count,
        max_players=int(info.max_players),
        players=players,
        observed_at=observed_at,
        game_directory=str(info.folder) if getattr(info, "folder", None) is not None else None,
        game_name=str(info.game) if getattr(info, "game", None) is not None else None,
        app_id=int(info.app_id) if getattr(info, "app_id", None) is not None else None,
    )
