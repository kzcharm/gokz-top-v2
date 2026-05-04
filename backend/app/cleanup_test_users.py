import argparse
import asyncio
import sys
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, exists, func, not_, or_
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.db import async_session_maker
from app.models import (
    Ban,
    LeaderboardPlayer,
    Player,
    PlayerFollow,
    PlayerProfileView,
    Record,
    User,
)


@dataclass(slots=True)
class CleanupTestUsersResult:
    dry_run: bool
    deleted_count: int
    steamid64s: list[int]


def _candidate_statement() -> Any:
    has_record = exists(
        select(Record.steamid64).where(col(Record.steamid64) == col(Player.steamid64))
    )
    has_leaderboard_row = exists(
        select(LeaderboardPlayer.steamid64).where(
            col(LeaderboardPlayer.steamid64) == col(Player.steamid64)
        )
    )
    has_follow = exists(
        select(PlayerFollow.follower_steamid64).where(
            or_(
                col(PlayerFollow.follower_steamid64) == col(Player.steamid64),
                col(PlayerFollow.followed_steamid64) == col(Player.steamid64),
            )
        )
    )
    has_profile_view = exists(
        select(PlayerProfileView.viewer_steamid64).where(
            or_(
                col(PlayerProfileView.viewer_steamid64) == col(Player.steamid64),
                col(PlayerProfileView.target_steamid64) == col(Player.steamid64),
            )
        )
    )
    has_ban = exists(select(Ban.id).where(col(Ban.steamid64) == col(Player.steamid64)))
    return (
        select(Player.steamid64)
        .outerjoin(User, col(User.steamid64) == col(Player.steamid64))
        .where(
            or_(
                col(User.steamid64).is_(None),
                func.coalesce(func.cardinality(col(User.roles)), 0) == 0,
            )
        )
        .where(col(Player.name) == "Test User")
        .where(col(Player.steamid64) != settings.SUPER_USER_STEAMID64)
        .where(not_(has_record))
        .where(not_(has_leaderboard_row))
        .where(not_(has_follow))
        .where(not_(has_profile_view))
        .where(not_(has_ban))
        .order_by(col(Player.created_at).desc(), col(Player.steamid64).desc())
    )


async def find_cleanup_candidates(*, session: AsyncSession) -> list[int]:
    return list((await session.exec(_candidate_statement())).all())


async def cleanup_test_users(
    *,
    session: AsyncSession,
    dry_run: bool,
) -> CleanupTestUsersResult:
    steamid64s = await find_cleanup_candidates(session=session)
    if dry_run or not steamid64s:
        return CleanupTestUsersResult(
            dry_run=dry_run,
            deleted_count=0,
            steamid64s=steamid64s,
        )

    await session.exec(delete(User).where(col(User.steamid64).in_(steamid64s)))
    await session.exec(delete(Player).where(col(Player.steamid64).in_(steamid64s)))
    await session.commit()
    return CleanupTestUsersResult(
        dry_run=False,
        deleted_count=len(steamid64s),
        steamid64s=steamid64s,
    )


def format_cleanup_result(result: CleanupTestUsersResult) -> str:
    mode = "DRY RUN" if result.dry_run else "DELETE"
    lines = [
        f"{mode}: found {len(result.steamid64s)} cleanup candidate(s).",
    ]
    if result.steamid64s:
        lines.append("Steam IDs:")
        lines.extend(str(steamid64) for steamid64 in result.steamid64s)
    if not result.dry_run:
        lines.append(f"Deleted {result.deleted_count} user/player pair(s).")
    return "\n".join(lines) + "\n"


async def _run_cli(*, delete_rows: bool) -> int:
    async with async_session_maker() as session:
        result = await cleanup_test_users(session=session, dry_run=not delete_rows)
    sys.stdout.write(format_cleanup_result(result))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Remove disposable helper-created Test User rows from the local app database."
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Delete candidate rows. Without this flag, the command only reports candidates.",
    )
    args = parser.parse_args()
    return asyncio.run(_run_cli(delete_rows=args.delete))


if __name__ == "__main__":
    raise SystemExit(main())
