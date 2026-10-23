"""Repair player date bounds for previously accepted native finishes."""

import argparse
import asyncio
import sys

from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import async_session_maker


async def repair_player_dates(
    session: AsyncSession, *, limit: int, after: int, apply: bool
) -> list[int]:
    """Bounded, resumable repair; identity and manually managed fields are untouched."""
    rows = await session.execute(
        text("""
            SELECT DISTINCT steamid64 FROM record
            WHERE native_server_id IS NOT NULL AND steamid64 > :after
            ORDER BY steamid64 LIMIT :limit
        """),
        {"after": after, "limit": limit},
    )
    players = list(rows.scalars())
    if apply and players:
        # Include mirrored history too, and never move the current bounds inward.
        await session.execute(
            text("""
                UPDATE player AS p
                SET created_at = LEAST(p.created_at, r.first_finish),
                    last_played_at = GREATEST(p.last_played_at, r.last_finish)
                FROM (
                    SELECT steamid64, MIN(created_at) AS first_finish,
                           MAX(created_at) AS last_finish
                    FROM record WHERE steamid64 = ANY(:players)
                    GROUP BY steamid64
                ) AS r
                WHERE p.steamid64 = r.steamid64
            """),
            {"players": players},
        )
        await session.commit()
    return players


async def _run(limit: int, after: int, apply: bool) -> None:
    async with async_session_maker() as session:
        players = await repair_player_dates(
            session, limit=limit, after=after, apply=apply
        )
    sys.stdout.write(
        f"{'Repaired' if apply else 'Selected (dry run)'} {len(players)} players; "
        f"next --after {players[-1] if players else after}\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--after", type=int, default=0)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.limit <= 10000 or args.after < 0:
        parser.error("Use --limit 1..10000 and a nonnegative --after SteamID")
    asyncio.run(_run(args.limit, args.after, args.apply))


if __name__ == "__main__":
    main()
