"""Benchmark the real rating rebuild, rolling back every batch.

From backend/: ../.venv/bin/python scripts/benchmark_ratings.py --scope SKZ
Reports and optional cProfile traces are written under .temp/rating-benchmark/.
This exercises database writes but never commits rating changes.
"""

import argparse
import asyncio
import cProfile
import json
import sys
from collections import defaultdict
from pathlib import Path
from time import perf_counter
from typing import Any

from sqlalchemy import event, text
from sqlmodel import col, select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.core.db import async_engine, async_session_maker  # noqa: E402
from app.crud.leaderboard_player import (  # noqa: E402
    load_leaderboard_player_keys,
    rebuild_leaderboard_players_batch,
)
from app.models import LeaderboardPlayer, ModeScope, ModeScopeId  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


async def benchmark(args: argparse.Namespace) -> dict[str, Any]:
    if settings.ENVIRONMENT != "local" or settings.POSTGRES_SERVER not in {
        "localhost",
        "127.0.0.1",
    }:
        raise ValueError("Run benchmarks against a local database only")
    sql_times: dict[str, float] = defaultdict(float)
    sql_calls: dict[str, int] = defaultdict(int)

    def before(
        _conn: Any, _cursor: Any, _sql: str, _params: Any, context: Any, _many: bool
    ) -> None:
        context.benchmark_start = perf_counter()

    def after(
        _conn: Any, _cursor: Any, sql: str, _params: Any, context: Any, _many: bool
    ) -> None:
        operation = sql.split()[0].upper()
        sql_times[operation] += perf_counter() - context.benchmark_start
        sql_calls[operation] += 1

    event.listen(async_engine.sync_engine, "before_cursor_execute", before)
    event.listen(async_engine.sync_engine, "after_cursor_execute", after)
    report: dict[str, Any] = {
        "scope": args.scope,
        "batch_size": args.batch_size,
        "existing_only": args.existing_only,
        "policy": "Every batch rolled back; excludes commit. No cache flush.",
        "rounds": [],
    }
    try:
        for repetition in range(args.rounds):
            sql_times.clear()
            sql_calls.clear()
            start = perf_counter()
            scope_id = int(ModeScopeId[args.scope])
            async with async_session_maker() as session:
                if args.existing_only:
                    statement = (
                        select(col(LeaderboardPlayer.steamid64))
                        .where(
                            col(LeaderboardPlayer.scope) == ModeScope[args.scope],
                        )
                        .order_by(col(LeaderboardPlayer.steamid64))
                    )
                    if args.limit:
                        statement = statement.limit(args.limit)
                    keys = [
                        (scope_id, player)
                        for player in (await session.exec(statement)).all()
                    ]
                else:
                    keys = await load_leaderboard_player_keys(
                        session=session,
                        scope_ids=[scope_id],
                    )
            selection_seconds = perf_counter() - start
            if args.limit:
                keys = keys[: args.limit]
            batches = []
            for offset in range(0, len(keys), args.batch_size):
                batch_start = perf_counter()
                async with async_session_maker() as session:
                    await session.exec(text("SET LOCAL statement_timeout = '120s'"))  # type: ignore[call-overload]
                    created, updated = await rebuild_leaderboard_players_batch(
                        session=session,
                        scope_id=scope_id,
                        steamid64s=[
                            player
                            for _, player in keys[offset : offset + args.batch_size]
                        ],
                    )
                    await session.rollback()
                batches.append(
                    {
                        "seconds": perf_counter() - batch_start,
                        "created": created,
                        "updated": updated,
                    }
                )
                print(  # noqa: T201
                    json.dumps(
                        {
                            "round": repetition + 1,
                            "processed": min(offset + args.batch_size, len(keys)),
                            "total": len(keys),
                            "sql_seconds": dict(sql_times),
                            **batches[-1],
                        }
                    ),
                    flush=True,
                )
            report["rounds"].append(
                {
                    "players": len(keys),
                    "seconds": perf_counter() - start,
                    "selection_seconds": selection_seconds,
                    "sql_seconds": dict(sql_times),
                    "sql_calls": dict(sql_calls),
                    "batches": batches,
                }
            )
            # Preserve completed rounds if a later pass is interrupted.
            args.output.write_text(json.dumps(report, indent=2) + "\n")
    finally:
        event.remove(async_engine.sync_engine, "before_cursor_execute", before)
        event.remove(async_engine.sync_engine, "after_cursor_execute", after)
        await async_engine.dispose()
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scope", choices=[scope.name for scope in ModeScopeId], default="SKZ"
    )
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--existing-only",
        action="store_true",
        help="Profile existing leaderboard players without PB eligibility discovery.",
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / ".temp/rating-benchmark/report.json"
    )
    parser.add_argument("--profile", action="store_true")
    args = parser.parse_args()
    if (
        args.rounds < 1
        or args.batch_size < 1
        or (args.limit is not None and args.limit < 1)
    ):
        parser.error("rounds, batch size, and limit must be positive")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    profiler = cProfile.Profile() if args.profile else None
    if profiler:
        profiler.enable()
    report = asyncio.run(benchmark(args))
    if profiler:
        profiler.disable()
        profiler.dump_stats(str(args.output.with_suffix(".prof")))
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))  # noqa: T201


if __name__ == "__main__":
    main()
