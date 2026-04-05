import argparse
import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import or_
from sqlmodel import col, select

from app import crud
from app.core.db import async_session_maker
from app.models import LeaderboardPlayer, Player, RecordScope, scope_to_id

logging.basicConfig(level=logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

STEAM_FETCH_BATCH_SIZE = 4


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


def _get_tqdm():
    try:
        from tqdm import tqdm
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Missing dependency 'tqdm'. Run `cd backend && uv sync` first."
        ) from exc
    return tqdm


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Rebuild player profile data from the Steam Web API. "
            "Defaults to players missing avatar hashes."
        ),
    )
    parser.add_argument(
        "--steamid64",
        action="append",
        type=int,
        dest="steamid64s",
        help=(
            "Optional player filter. Repeat to rebuild multiple players. "
            "When omitted, defaults to players missing avatar hashes."
        ),
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process all existing players instead of only those missing avatar hashes.",
    )
    parser.add_argument(
        "--leaderboard",
        type=_parse_scope,
        default=None,
        help=(
            "Optional leaderboard scope selector (OVR, KZT, SKZ, VNL). "
            "Selects players by rating DESC instead of the default missing-avatar filter."
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional limit on how many selected players to process.",
    )
    return parser


def _dedupe_steamid64s(steamid64s: Sequence[int]) -> list[int]:
    return list(dict.fromkeys(steamid64s))


def _iter_batches[T](items: Sequence[T], *, batch_size: int) -> list[list[T]]:
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    return [
        list(items[index : index + batch_size])
        for index in range(0, len(items), batch_size)
    ]


def _parse_scope(raw_scope: str) -> RecordScope:
    normalized_scope = raw_scope.strip().upper()
    try:
        return RecordScope[normalized_scope]
    except KeyError as exc:
        valid_scopes = ", ".join(scope.name for scope in RecordScope)
        raise argparse.ArgumentTypeError(
            f"Invalid leaderboard scope {raw_scope!r}. Expected one of: {valid_scopes}"
        ) from exc


async def load_target_steamid64s(
    *,
    steamid64s: Sequence[int] | None = None,
    only_missing_avatar: bool = True,
    leaderboard_scope: RecordScope | None = None,
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
            or_(Player.avatar_hash.is_(None), Player.avatar_hash == "")
        )

    async with async_session_maker() as session:
        return list((await session.exec(statement)).all())


async def rebuild_player_profiles(
    *,
    steamid64s: Sequence[int] | None = None,
    only_missing_avatar: bool = True,
    leaderboard_scope: RecordScope | None = None,
    limit: int | None = None,
) -> RebuildPlayerProfileResult:
    target_steamid64s = await load_target_steamid64s(
        steamid64s=steamid64s,
        only_missing_avatar=only_missing_avatar,
        leaderboard_scope=leaderboard_scope,
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

    result = RebuildPlayerProfileResult(
        selected=len(target_steamid64s),
        created=created,
        updated=updated,
        skipped=skipped,
    )
    return result


async def _main_async(argv: list[str] | None = None) -> None:
    args = _build_parser().parse_args(argv)
    try:
        await rebuild_player_profiles(
            steamid64s=args.steamid64s,
            only_missing_avatar=not args.all,
            leaderboard_scope=args.leaderboard,
            limit=args.limit,
        )
    except RebuildPlayerProfileInterruptedError as exc:
        result = exc.result
        processed = result.created + result.updated + result.skipped
        print(
            (
                "\nInterrupted. "
                f"Processed {processed}/{result.selected} players "
                f"(created={result.created}, updated={result.updated}, skipped={result.skipped})."
            ),
            flush=True,
        )
        raise SystemExit(130) from exc


def main(argv: list[str] | None = None) -> None:
    asyncio.run(_main_async(argv))


if __name__ == "__main__":
    main()
