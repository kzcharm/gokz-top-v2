"""Measure local OVR NUB rebuilds with forced point changes and rollback."""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from time import perf_counter

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import settings  # noqa: E402
from app.core.db import async_engine, async_session_maker  # noqa: E402
from app.crud.record import rebuild_record_pb_points_bucket  # noqa: E402
from app.models import ModeScope, RecordType, mode_scope_to_id  # noqa: E402


async def benchmark(courses: list[int], rounds: int) -> list[dict[str, int | float]]:
    if settings.ENVIRONMENT != "local" or settings.POSTGRES_SERVER not in {
        "localhost",
        "127.0.0.1",
    }:
        raise ValueError("Points benchmarks require the local database")
    results = []
    for repetition in range(rounds):
        for course in courses:
            async with async_session_maker() as session:
                await session.execute(text("SET LOCAL lock_timeout='5s'"))
                await session.execute(text("SET LOCAL statement_timeout='120s'"))
                # Setup excluded from timing. This exercises a full formula change.
                await session.execute(
                    text(
                        "UPDATE record_pb SET points=1 WHERE scope='OVR' AND type='NUB' AND course_id=:course"
                    ),
                    {"course": course},
                )
                start = perf_counter()
                changed = await rebuild_record_pb_points_bucket(
                    session=session,
                    course_id=course,
                    scope_id=mode_scope_to_id(ModeScope.OVR),
                    record_type=RecordType.NUB,
                )
                elapsed = perf_counter() - start
                await session.rollback()
            row = {
                "round": repetition + 1,
                "course": course,
                "changed": changed,
                "seconds": elapsed,
            }
            results.append(row)
            print(json.dumps(row), flush=True)  # noqa: T201
    await async_engine.dispose()
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--course", type=int, nargs="+", required=True)
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = asyncio.run(benchmark(args.course, args.rounds))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
