"""Read-only first-completion benchmark against the configured PostgreSQL database.

From backend/: ../.venv/bin/python scripts/benchmark_first_completions.py
Reports go to .temp/first-completion; no database objects or records are changed.
"""

import argparse
import asyncio
import json
import math
import statistics
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from time import perf_counter
from typing import Any

import httpx
from fastapi import FastAPI
from sqlalchemy import func, text
from sqlalchemy.orm import aliased
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

# Support invocation as a script without requiring an editable install.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.deps import get_db  # noqa: E402
from app.api.v1.records import router  # noqa: E402
from app.core.db import async_engine  # noqa: E402
from app.crud.record import first_completion_statement  # noqa: E402
from app.models import ModeScope, Record, RecordType, mode_scope_modes  # noqa: E402


def latency_summary(samples: list[float]) -> dict[str, float]:
    ordered = sorted(samples)
    return {
        "first_ms": samples[0],
        "p95_ms": ordered[math.ceil(len(samples) * 0.95) - 1],
        "warm_p50_ms": statistics.median(samples[1:]),
        "warm_p95_ms": sorted(samples[1:])[math.ceil((len(samples) - 1) * 0.95) - 1],
        "max_ms": ordered[-1],
    }


async def benchmark(args: argparse.Namespace) -> dict[str, Any]:
    report: dict[str, Any] = {
        "endpoint_transport": "in-process ASGI (excludes network and server startup)",
        "latency_policy": "p95 includes first execution; warm p95 is reported separately. No server cache flush is performed.",
        "rounds": args.rounds,
        "limits_ms": {"database_p95": 200, "endpoint_p95": 500},
        "cases": [],
    }
    async with AsyncSession(async_engine) as session:
        await session.exec(
            text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        )  # type: ignore[call-overload]
        await session.exec(text("SET LOCAL statement_timeout = '30s'"))  # type: ignore[call-overload]
        if args.identifier:
            players = [int(value) for value in args.identifier]
        else:
            # Sample pages rather than grouping the entire history table.
            sample = (
                await session.execute(
                    text(
                        "SELECT steamid64, count(*) AS n FROM record "
                        "TABLESAMPLE SYSTEM (1) REPEATABLE (42) "
                        "GROUP BY steamid64 ORDER BY n, steamid64"
                    )
                )
            ).all()
            if not sample:
                raise RuntimeError(
                    "No records available; provide representative player SteamIDs"
                )
            players = list(
                dict.fromkeys(
                    int(sample[index][0])
                    for index in (
                        len(sample) // 10,
                        len(sample) * 3 // 4,
                        len(sample) - 1,
                    )
                )
            )
        report["players"] = [
            {
                "steamid64": str(player),
                "history_rows": (
                    await session.execute(
                        text("SELECT count(*) FROM record WHERE steamid64 = :player"),
                        {"player": player},
                    )
                ).scalar_one(),
            }
            for player in players
        ]

        async def readonly_session() -> AsyncIterator[AsyncSession]:
            yield session

        app = FastAPI()
        app.include_router(router, prefix="/v1")
        app.dependency_overrides[get_db] = readonly_session
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://benchmark"
        ) as client:
            for player in players:
                for scope in ModeScope:
                    for record_type in (RecordType.NUB, RecordType.PRO):
                        for is_bonus in (False, True):
                            grouped = first_completion_statement(
                                steamid64=player,
                                scope=scope,
                                record_type=record_type,
                                is_bonus=is_bonus,
                            )
                            courses = grouped.with_only_columns(
                                col(Record.map_id), col(Record.stage)
                            ).subquery()
                            history = aliased(Record)
                            minimum = select(func.min(history.created_at)).where(
                                col(history.steamid64) == player,
                                col(history.map_id) == courses.c.map_id,
                                col(history.stage) == courses.c.stage,
                                col(history.is_valid) == True,  # noqa: E712
                                col(history.mode).in_(list(mode_scope_modes(scope))),
                            )
                            if record_type.is_pro:
                                minimum = minimum.where(col(history.teleports) == 0)
                            baseline = select(
                                courses.c.map_id,
                                courses.c.stage,
                                minimum.scalar_subquery(),
                            ).order_by(courses.c.map_id, courses.c.stage)
                            case: dict[str, Any] = {
                                "steamid64": str(player),
                                "scope": scope.value,
                                "type": record_type.value,
                                "is_bonus": is_bonus,
                            }
                            expected = None
                            for name, statement in (
                                ("grouped", grouped),
                                ("correlated", baseline),
                            ):
                                timings = []
                                for _ in range(args.rounds + 1):
                                    started = perf_counter()
                                    rows = (await session.execute(statement)).all()
                                    timings.append((perf_counter() - started) * 1000)
                                if expected is None:
                                    expected = rows
                                elif rows != expected:
                                    raise AssertionError(
                                        "Grouped and correlated results differ"
                                    )
                                sql = str(
                                    statement.compile(
                                        dialect=async_engine.dialect,
                                        compile_kwargs={"literal_binds": True},
                                    )
                                )
                                plan = (
                                    await session.execute(
                                        text(
                                            f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {sql}"
                                        )
                                    )
                                ).scalar_one()
                                case[name] = {**latency_summary(timings), "plan": plan}
                            timings = []
                            for _ in range(args.rounds + 1):
                                started = perf_counter()
                                response = await client.get(
                                    "/v1/records/pb/first-completions",
                                    params={
                                        "identifier": str(player),
                                        "scope": scope.value,
                                        "type": record_type.value,
                                        "is_bonus": str(is_bonus).lower(),
                                    },
                                )
                                response.raise_for_status()
                                timings.append((perf_counter() - started) * 1000)
                            case["endpoint"] = latency_summary(timings)
                            case["courses"] = len(expected or [])
                            report["cases"].append(case)
                            sys.stdout.write(
                                f"{player} {scope.value} {record_type.value} bonus={is_bonus}: "
                                f"grouped warm p95={case['grouped']['warm_p95_ms']:.1f}ms, "
                                f"endpoint warm p95={case['endpoint']['warm_p95_ms']:.1f}ms\n"
                            )
                            sys.stdout.flush()
        await session.rollback()
    report["persistence_eligible"] = len(players) >= 3 and all(
        case["grouped"]["p95_ms"] <= 200 and case["endpoint"]["p95_ms"] <= 500
        for case in report["cases"]
    )
    return report


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--identifier", action="append", help="Player SteamID64; repeat for each player"
    )
    parser.add_argument("--rounds", type=int, default=20)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[2]
        / ".temp/first-completion/benchmark.json",
    )
    args = parser.parse_args()
    if args.rounds < 2:
        parser.error("--rounds must be at least 2")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        report = await benchmark(args)
    except Exception as exc:
        # Avoid including connection URLs or credentials from driver exceptions.
        args.output.write_text(
            json.dumps(
                {"persistence_eligible": False, "error_type": type(exc).__name__},
                indent=2,
            )
        )
        raise
    finally:
        await async_engine.dispose()
    args.output.write_text(json.dumps(report, indent=2))
    sys.stdout.write(
        f"Report: {args.output}\nPersistence eligible: {report['persistence_eligible']}\n"
    )


if __name__ == "__main__":
    asyncio.run(main())
