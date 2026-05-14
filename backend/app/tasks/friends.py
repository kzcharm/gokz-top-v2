import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlmodel import col, select

from app import crud
from app.core.db import async_session_maker
from app.models import LeaderboardPlayer, ModeScope, Player
from app.services.player_friends import sync_player_friends

logger = logging.getLogger(__name__)

__all__ = [
    "SyncPlayerFriendsInterruptedError",
    "SyncPlayerFriendsResult",
    "load_target_steamid64s",
    "sync_player_friends_for_players",
]


@dataclass(frozen=True, slots=True)
class SyncPlayerFriendsResult:
    selected: int = 0
    synced: int = 0
    rate_limited: int = 0
    private: int = 0
    failed: int = 0


class SyncPlayerFriendsInterruptedError(Exception):
    def __init__(self, result: SyncPlayerFriendsResult) -> None:
        super().__init__("Player friends sync interrupted")
        self.result = result


def _get_tqdm() -> Any:
    try:
        from tqdm import tqdm  # type: ignore[import-untyped]
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Missing dependency 'tqdm'. Run `cd backend && uv sync` first."
        ) from exc
    return tqdm


def _dedupe_steamid64s(steamid64s: Sequence[int]) -> list[int]:
    return list(dict.fromkeys(steamid64s))


async def load_target_steamid64s(
    *,
    steamid64s: Sequence[int] | None = None,
    leaderboard_scope: ModeScope | None = None,
) -> list[int]:
    if steamid64s:
        return _dedupe_steamid64s(steamid64s)

    if leaderboard_scope is not None:
        statement = (
            select(LeaderboardPlayer.steamid64)
            .where(
                col(LeaderboardPlayer.scope) == leaderboard_scope,
                col(LeaderboardPlayer.rating) > 0,
            )
            .order_by(
                col(LeaderboardPlayer.rating).desc(),
                col(LeaderboardPlayer.steamid64).asc(),
            )
        )
    else:
        statement = select(Player.steamid64).order_by(col(Player.steamid64).asc())

    async with async_session_maker() as session:
        return list((await session.exec(statement)).all())


async def sync_player_friends_for_players(
    *,
    steamid64s: Sequence[int] | None = None,
    leaderboard_scope: ModeScope | None = None,
    limit: int | None = None,
) -> SyncPlayerFriendsResult:
    target_steamid64s = await load_target_steamid64s(
        steamid64s=steamid64s,
        leaderboard_scope=leaderboard_scope,
    )
    if limit is not None:
        target_steamid64s = target_steamid64s[:limit]

    if not target_steamid64s:
        logger.warning("No player rows matched the selected filters.")
        return SyncPlayerFriendsResult()

    tqdm = _get_tqdm()
    progress = tqdm(total=len(target_steamid64s), desc="player friends", unit="player")

    synced = 0
    rate_limited = 0
    private = 0
    failed = 0

    try:
        for steamid64 in target_steamid64s:
            async with async_session_maker() as session:
                player = await crud.get_player_by_steamid64(
                    session=session,
                    steamid64=steamid64,
                )
                if player is None:
                    failed += 1
                    status = "failed"
                else:
                    result = await sync_player_friends(session=session, player=player)
                    status = result.kind
                    if result.kind == "success":
                        synced += 1
                    elif result.kind == "rate_limited":
                        rate_limited += 1
                    elif result.kind in {"private_profile", "private_friends"}:
                        private += 1
                    else:
                        failed += 1

                progress.update(1)
                progress.set_postfix_str(f"steamid64={steamid64} status={status}")
    except KeyboardInterrupt as exc:
        progress.close()
        raise SyncPlayerFriendsInterruptedError(
            SyncPlayerFriendsResult(
                selected=len(target_steamid64s),
                synced=synced,
                rate_limited=rate_limited,
                private=private,
                failed=failed,
            )
        ) from exc
    finally:
        progress.close()

    return SyncPlayerFriendsResult(
        selected=len(target_steamid64s),
        synced=synced,
        rate_limited=rate_limited,
        private=private,
        failed=failed,
    )
