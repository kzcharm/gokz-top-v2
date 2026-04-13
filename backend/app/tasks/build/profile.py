import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import or_
from sqlmodel import col, select

from app import crud
from app.core.db import async_session_maker
from app.models import (
    LeaderboardPlayer,
    Player,
    RecordScope,
    get_datetime_utc,
    scope_to_id,
)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

STEAM_FETCH_BATCH_SIZE = 4
__all__ = [
    "RebuildPlayerProfileInterruptedError",
    "RebuildPlayerProfileResult",
    "load_target_steamid64s",
    "rebuild_player_profiles",
]


@dataclass(frozen=True, slots=True)
class RebuildPlayerProfileResult:
    selected: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0


class RebuildPlayerProfileInterruptedError(Exception):
    def __init__(self, result: RebuildPlayerProfileResult) -> None:
        super().__init__("Player profile rebuild interrupted")
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


def _iter_batches[T](items: Sequence[T], *, batch_size: int) -> list[list[T]]:
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    return [
        list(items[index : index + batch_size])
        for index in range(0, len(items), batch_size)
    ]


async def load_target_steamid64s(
    *,
    steamid64s: Sequence[int] | None = None,
    only_missing_avatar: bool = True,
    leaderboard_scope: RecordScope | None = None,
    stale_before: datetime | None = None,
) -> list[int]:
    if steamid64s:
        return _dedupe_steamid64s(steamid64s)

    if leaderboard_scope is not None:
        statement = (
            select(LeaderboardPlayer.steamid64)
            .where(
                col(LeaderboardPlayer.scope) == scope_to_id(leaderboard_scope),
                col(LeaderboardPlayer.rating) > 0,
            )
            .order_by(
                col(LeaderboardPlayer.rating).desc(),
                col(LeaderboardPlayer.steamid64).asc(),
            )
        )
    else:
        statement = select(Player.steamid64).order_by(col(Player.steamid64).asc())
    if leaderboard_scope is None and only_missing_avatar:
        statement = statement.where(
            or_(col(Player.avatar_hash).is_(None), col(Player.avatar_hash) == "")
        )
    if leaderboard_scope is None and stale_before is not None:
        statement = statement.where(
            or_(col(Player.updated_at).is_(None), col(Player.updated_at) <= stale_before)
        )

    async with async_session_maker() as session:
        return list((await session.exec(statement)).all())


async def rebuild_player_profiles(
    *,
    steamid64s: Sequence[int] | None = None,
    only_missing_avatar: bool = True,
    leaderboard_scope: RecordScope | None = None,
    stale_days: int | None = None,
    limit: int | None = None,
) -> RebuildPlayerProfileResult:
    stale_before = (
        get_datetime_utc() - timedelta(days=stale_days)
        if stale_days is not None
        else None
    )
    target_steamid64s = await load_target_steamid64s(
        steamid64s=steamid64s,
        only_missing_avatar=only_missing_avatar,
        leaderboard_scope=leaderboard_scope,
        stale_before=stale_before,
    )

    if limit is not None:
        target_steamid64s = target_steamid64s[:limit]

    if not target_steamid64s:
        logger.warning("No player rows matched the selected filters.")
        return RebuildPlayerProfileResult()

    tqdm = _get_tqdm()
    progress = tqdm(total=len(target_steamid64s), desc="player profiles", unit="player")

    created = 0
    updated = 0
    skipped = 0

    try:
        for steamid64_batch in _iter_batches(
            target_steamid64s,
            batch_size=STEAM_FETCH_BATCH_SIZE,
        ):
            async with async_session_maker() as session:
                steam_data_by_steamid64 = await crud._fetch_players_from_steam_api(
                    steamid64_batch
                )

                for steamid64 in steamid64_batch:
                    player, was_created = await crud.create_or_update_player_from_steam_data_if_fetched(
                        session=session,
                        steamid64=steamid64,
                        steam_data=steam_data_by_steamid64.get(steamid64),
                    )

                    if player is None:
                        skipped += 1
                        status = "skipped"
                    elif was_created:
                        created += 1
                        status = "created"
                    else:
                        updated += 1
                        status = "updated"

                    progress.update(1)
                    progress.set_postfix_str(f"steamid64={steamid64} status={status}")
    except KeyboardInterrupt as exc:
        progress.close()
        raise RebuildPlayerProfileInterruptedError(
            RebuildPlayerProfileResult(
                selected=len(target_steamid64s),
                created=created,
                updated=updated,
                skipped=skipped,
            )
        ) from exc
    finally:
        progress.close()

    return RebuildPlayerProfileResult(
        selected=len(target_steamid64s),
        created=created,
        updated=updated,
        skipped=skipped,
    )
