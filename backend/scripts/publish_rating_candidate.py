"""Publish a complete offline OVR rating candidate to the local preview database.

Rebuilds missing/ineligible leaderboard rows through the normal builder, then
atomically publishes raw ratings and E/H converters. Other leaderboard counters
and per-PB contributions remain the responsibility of the normal refresh jobs.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import gzip
import json
import sys
from dataclasses import asdict
from math import isfinite
from pathlib import Path
from typing import Any

import numpy as np
import psycopg
from psycopg.types.json import Jsonb

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.core.db import async_engine, async_session_maker  # noqa: E402
from app.core.rank_system import get_rank_system_settings  # noqa: E402
from app.crud.leaderboard_player import (  # noqa: E402
    rebuild_leaderboard_player_count,
    rebuild_leaderboard_players_batch,
)
from app.models import ModeScope, mode_scope_to_id  # noqa: E402
from scripts.tune_ratings import FIELDS, checksum  # noqa: E402


def load_candidate(
    snapshot: Path, candidate: Path
) -> tuple[list[tuple[int | float, ...]], dict[str, Any]]:
    metadata = json.loads((snapshot / "metadata.json").read_text())
    report = json.loads(candidate.with_suffix(".json").read_text())
    curves = json.loads(candidate.with_suffix(".converters.json").read_text())
    runtime = get_rank_system_settings()
    parameters = json.loads(json.dumps(asdict(runtime.rating), default=str))
    if metadata["scope"] != "OVR" or report["scope"] != "OVR":
        raise ValueError("Only complete OVR candidates can be published")
    if tuple(report["fields"]) != FIELDS:
        raise ValueError("Publish requires all nine rating fields")
    if not all(field in curves["metrics"] for field in FIELDS[:3]):
        raise ValueError("Publish requires overall and E/H display curves")
    for name, expected in metadata["sha256"].items():
        if checksum(snapshot / name) != expected:
            raise ValueError("Snapshot checksum mismatch")
    if any(
        source["snapshot_sha256"] != metadata["sha256"] for source in (report, curves)
    ):
        raise ValueError("Candidate and converter snapshots differ")
    if any(source["rating_settings"] != parameters for source in (report, curves)):
        raise ValueError("Candidate parameters must match rank-system.toml")
    if (
        curves["source_scope"] != "OVR"
        or curves["metrics"]["rating"] != runtime.display_anchors
    ):
        raise ValueError("Overall display anchors must match rank-system.toml")
    runs = np.load(snapshot / "runs.npy", mmap_mode="r", allow_pickle=False)
    players, counts = np.unique(runs["player"], return_counts=True)
    finishes = dict(zip(map(int, players), map(int, counts), strict=True))
    with candidate.open() as source:
        rows = [
            (
                int(row["steamid64"]),
                *(
                    float(row[field]) if field == "rating" else int(row[field])
                    for field in FIELDS
                ),
                finishes[int(row["steamid64"])],
            )
            for row in csv.DictReader(source)
        ]
    if len(rows) != len(players) or {row[0] for row in rows} != set(finishes):
        raise ValueError("Candidate must contain every snapshot player exactly once")
    if any(
        source[key] != len(players)
        for source, key in (
            (metadata, "players"),
            (report, "players"),
            (curves, "sample_size"),
        )
    ):
        raise ValueError("Candidate population metadata does not match the snapshot")
    if any(
        not isfinite(value) or value < 0 or value > runtime.rating.target_max_raw_rating
        for row in rows
        for value in row[1:-1]
    ):
        raise ValueError("Candidate rating is outside the allowed range")
    return rows, curves


async def publish(snapshot: Path, candidate: Path, backup: Path) -> dict[str, int]:
    if settings.ENVIRONMENT != "local" or settings.POSTGRES_SERVER not in {
        "localhost",
        "127.0.0.1",
    }:
        raise ValueError(
            "Publishing candidates is restricted to the local preview database"
        )
    rows, curves = load_candidate(snapshot, candidate)
    uri = str(settings.SQLALCHEMY_DATABASE_URI).replace(
        "postgresql+psycopg", "postgresql"
    )
    with psycopg.connect(uri) as connection:
        existing = {
            row[0]
            for row in connection.execute(
                "SELECT steamid64 FROM leaderboard_player WHERE scope='OVR'"
            )
        }
        backup.mkdir(parents=True, exist_ok=False)
        for table, condition in (
            ("leaderboard_player", "scope='OVR'"),
            ("skill_rating_converter", "scope='OVR' AND skill IN ('easy','hard')"),
        ):
            with gzip.open(backup / f"{table}.jsonl.gz", "wt") as output:
                for row in connection.execute(
                    f"SELECT row_to_json(t) FROM {table} t WHERE {condition}"
                ):
                    output.write(json.dumps(row[0]) + "\n")
    players = {row[0] for row in rows}
    repair = sorted(existing.symmetric_difference(players))
    for start in range(0, len(repair), 500):
        async with async_session_maker() as session:
            await rebuild_leaderboard_players_batch(
                session=session,
                scope_id=mode_scope_to_id(ModeScope.OVR),
                steamid64s=repair[start : start + 500],
            )
            await session.commit()
    with psycopg.connect(uri) as connection:
        connection.execute("SET LOCAL lock_timeout='30s'")
        columns = ("steamid64", *FIELDS, "unique_map_finishes")
        definitions = ", ".join(
            f"{column} numeric(11,6)" if column == "rating" else f"{column} bigint"
            for column in columns
        )
        connection.execute(
            f"CREATE TEMP TABLE candidate ({definitions}) ON COMMIT DROP"
        )
        with connection.cursor().copy("COPY candidate FROM STDIN") as copy:
            for row in rows:
                copy.write_row(row)
        connection.execute("CREATE UNIQUE INDEX ON candidate(steamid64)")
        connection.execute("ANALYZE candidate")
        assignments = ", ".join(
            f"{field}=c.{field}" for field in (*FIELDS, "unique_map_finishes")
        )
        result = connection.execute(
            f"UPDATE leaderboard_player p SET {assignments}, updated_at=now() FROM candidate c WHERE p.scope='OVR' AND p.steamid64=c.steamid64"
        )
        if result.rowcount != len(rows):
            raise ValueError("Leaderboard population changed; extract a fresh snapshot")
        for metric in ("easy", "hard"):
            connection.execute(
                """INSERT INTO skill_rating_converter(scope,skill,anchors,sample_size,updated_at)
                VALUES ('OVR',%s,%s,%s,now()) ON CONFLICT(scope,skill) DO UPDATE
                SET anchors=excluded.anchors,sample_size=excluded.sample_size,updated_at=excluded.updated_at""",
                (
                    metric,
                    Jsonb(curves["metrics"][f"rating_{metric}"]),
                    curves["sample_size"],
                ),
            )
    async with async_session_maker() as session:
        await rebuild_leaderboard_player_count(session=session, scope=ModeScope.OVR)
        await session.commit()
    await async_engine.dispose()
    return {"published": len(rows), "repaired": len(repair)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--backup", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(publish(args.snapshot, args.candidate, args.backup))))  # noqa: T201
