import argparse
import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass

from app import crud
from app.core.db import async_session_maker
from app.models import RecordScope, RecordScopeId

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class LeaderboardRebuildResult:
    selected: int
    created: int
    updated: int


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
        description="Rebuild leaderboard_player rows for selected scopes and players.",
    )
    parser.add_argument(
        "--scope",
        action="append",
        choices=[scope.name for scope in RecordScope],
        dest="scopes",
        help="Optional scope filter. Repeat to rebuild multiple scopes. Defaults to all scopes.",
    )
    parser.add_argument(
        "--steamid64",
        action="append",
        type=int,
        dest="steamid64s",
        help="Optional player filter. Repeat to rebuild multiple players. Defaults to all players.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional limit on how many selected rows to process.",
    )
    return parser


def _resolve_scope_ids(scope_names: Sequence[str] | None) -> list[int] | None:
    if not scope_names:
        return None
    return [int(RecordScopeId[name]) for name in scope_names]


async def _main_async(argv: list[str] | None = None) -> None:
    args = _build_parser().parse_args(argv)
    scope_ids = _resolve_scope_ids(args.scopes)
    steamid64s: list[int] | None = args.steamid64s if args.steamid64s else None
    await rebuild_leaderboard_rows(
        scope_ids=scope_ids,
        steamid64s=steamid64s,
        limit=args.limit,
    )


async def rebuild_leaderboard_rows(
    *,
    scope_ids: Sequence[int] | None,
    steamid64s: Sequence[int] | None,
    limit: int | None,
    prioritize_existing_rating: bool = False,
) -> LeaderboardRebuildResult:
    steamid64_list = list(steamid64s) if steamid64s is not None else None

    async with async_session_maker() as session:
        keys = await crud.load_leaderboard_player_keys(
            session=session,
            scope_ids=scope_ids,
            steamid64s=steamid64_list,
            prioritize_existing_rating=prioritize_existing_rating,
        )

    if limit is not None:
        keys = keys[:limit]

    if not keys:
        logger.warning("No leaderboard_player rows matched the selected filters.")
        return LeaderboardRebuildResult(selected=0, created=0, updated=0)

    logger.info("Rebuilding %s leaderboard_player row(s)", len(keys))
    tqdm = _get_tqdm()
    total_created = 0
    total_updated = 0
    progress = tqdm(keys, total=len(keys), desc="leaderboard rows", unit="row")
    for scope_id, steamid64 in progress:
        async with async_session_maker() as session:
            created, updated = await crud.rebuild_leaderboard_players_for_keys(
                session=session,
                keys=[(scope_id, steamid64)],
            )
            await session.commit()
        total_created += created
        total_updated += updated
        progress.set_postfix_str(
            f"scope={RecordScopeId(scope_id).name} steamid64={steamid64}"
        )

    logger.info(
        "Finished rebuilding leaderboard_player rows=%s created=%s updated=%s",
        len(keys),
        total_created,
        total_updated,
    )
    return LeaderboardRebuildResult(
        selected=len(keys),
        created=total_created,
        updated=total_updated,
    )


def main(argv: list[str] | None = None) -> None:
    asyncio.run(_main_async(argv))


if __name__ == "__main__":
    main()
