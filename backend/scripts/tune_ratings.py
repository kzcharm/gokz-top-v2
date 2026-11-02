"""Snapshot rating inputs once, then compare parameters without database writes.

From backend/: python scripts/tune_ratings.py snapshot --scope SKZ
Then: python scripts/tune_ratings.py evaluate --scope SKZ --decay 0.98
PB point formula changes need a fresh snapshot with recalculated points.
Results include raw ratings and optional OVR-calibrated display levels.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import sys
from dataclasses import asdict, replace
from datetime import UTC, datetime
from decimal import Decimal
from itertools import groupby
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np
from sqlalchemy import text
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.db import async_engine  # noqa: E402
from app.core.rank_system import RatingSettings, get_rank_system_settings  # noqa: E402
from app.crud.leaderboard_player import (  # noqa: E402
    ELIGIBLE_UNIQUE_MAP_FINISHES,
    calculate_weighted_rating,
)
from app.crud.record_filter import load_scoped_course_tiers  # noqa: E402
from app.models import MapCourse, MapSkill, ModeScope  # noqa: E402
from app.services.course_points import calculate_course_pb_points  # noqa: E402
from app.services.skill_rating import SKILLS, calculate_skill_rating  # noqa: E402
from app.services.skill_rating_converter import (  # noqa: E402
    calibrate,
    convert_skill_rating,
)

ROOT = Path(__file__).resolve().parents[2]
DTYPE = np.dtype(
    [("player", "<i8"), ("course", "<i4"), ("map", "<i4"), ("points", "<i4")]
)
FIELDS = (
    "rating",
    "rating_easy",
    "rating_hard",
    *(f"rating_{skill}" for skill in SKILLS),
)
FIELD_GROUPS = {
    "all": FIELDS,
    "overall-and-difficulty": FIELDS[:3],
    "overall": FIELDS[:1],
    "difficulty": FIELDS[1:3],
    "skills": FIELDS[3:],
}
SOURCE_SQL = """
    SELECT pb.steamid64, pb.course_id, mc.map_id, MAX(pb.points)
    FROM record_pb pb
    JOIN map_course mc ON mc.id = pb.course_id AND mc.stage = 0
    JOIN map m ON m.id = mc.map_id AND m.validated IS TRUE
    WHERE pb.scope = %s::mode_scope
      AND NOT EXISTS (
          SELECT 1 FROM ban b WHERE b.steamid64 = pb.steamid64
          AND (b.expires_at IS NULL OR b.expires_at >= CURRENT_TIMESTAMP)
      )
    GROUP BY pb.steamid64, pb.course_id, mc.map_id
    ORDER BY pb.steamid64, pb.course_id
"""
RECALCULATE_SOURCE_SQL = """
    SELECT pb.steamid64, pb.course_id, mc.map_id, pb.type,
           ROUND(pb.time * 1000)::bigint
    FROM record_pb pb
    JOIN map_course mc ON mc.id = pb.course_id AND mc.stage = 0
    JOIN map m ON m.id = mc.map_id AND m.validated IS TRUE
    WHERE pb.scope = %s::mode_scope
      AND NOT EXISTS (
          SELECT 1 FROM ban b WHERE b.steamid64 = pb.steamid64
          AND (b.expires_at IS NULL OR b.expires_at >= CURRENT_TIMESTAMP)
      )
    ORDER BY pb.course_id, pb.type, pb.time, pb.record_uuid
"""


def recalculate_snapshot_points(source: Path, tiers: dict[str, int]) -> np.ndarray:
    """Recalculate complete PB buckets before selecting eligible rating players.

    Low-completion players still affect ranks and percentile points. The SQL
    stream has the exact time/UUID ordering used by the production rebuild.
    """
    destination = source.with_name("recalculated.csv")
    with (
        source.open(newline="") as incoming,
        destination.open("w", newline="") as output,
    ):
        writer = csv.writer(output)
        for course, course_rows in groupby(
            csv.reader(incoming), key=lambda row: row[1]
        ):
            best: dict[int, int] = {}
            map_id = 0
            for kind, bucket in groupby(course_rows, key=lambda row: row[3]):
                rows = list(bucket)
                wr_time_ms = int(rows[0][4])
                map_id = int(rows[0][2])
                for rank, row in enumerate(rows, start=1):
                    player = int(row[0])
                    points = calculate_course_pb_points(
                        rank=rank,
                        total=len(rows),
                        time_ms=int(row[4]),
                        wr_time_ms=wr_time_ms,
                        tier=tiers[course],
                        is_pro_only=kind == "PRO",
                    )
                    best[player] = max(best.get(player, 0), points)
            writer.writerows(
                (player, course, map_id, points) for player, points in best.items()
            )
    if destination.stat().st_size:
        runs = np.atleast_1d(np.loadtxt(destination, delimiter=",", dtype=DTYPE))
        runs.sort(order=["player", "course"])
    else:
        runs = np.empty(0, dtype=DTYPE)
    destination.unlink()
    return runs


def checksum(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def eligible_runs(runs: np.ndarray) -> np.ndarray:
    players, counts = np.unique(runs["player"], return_counts=True)
    return runs[
        np.isin(runs["player"], players[counts >= ELIGIBLE_UNIQUE_MAP_FINISHES])
    ]


async def snapshot(
    path: Path, scope: ModeScope, *, recalculate_points: bool = False
) -> dict[str, Any]:
    start = perf_counter()
    # Each snapshot is immutable; a new directory prevents mixed-generation files.
    path.mkdir(parents=True, exist_ok=False)
    async with async_engine.connect() as connection:
        await connection.execute(
            text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        )
        async with AsyncSession(bind=connection) as session:
            courses = (
                await session.exec(select(MapCourse).where(col(MapCourse.stage) == 0))
            ).all()
            tiers = await load_scoped_course_tiers(
                session=session,
                scope=scope,
                course_keys=[(course.map_id, 0) for course in courses],
            )
            analyses = (
                await session.exec(
                    select(
                        col(MapSkill.map_id),
                        *(getattr(MapSkill, skill) for skill in SKILLS),
                    )
                )
            ).all()
            course_tiers = {
                str(course.id): tiers[(course.map_id, 0)] for course in courses
            }
            metadata_maps = {
                "tiers": course_tiers,
                "skills": {
                    str(row[0]): [str(value) for value in row[1:]] for row in analyses
                },
            }
            raw = await connection.get_raw_connection()
            driver = raw.driver_connection
            if driver is None:
                raise RuntimeError("PostgreSQL connection is unavailable")
            csv_path = path / "extracting.csv"
            with csv_path.open("wb") as destination:
                async with driver.cursor().copy(
                    f"COPY ({RECALCULATE_SOURCE_SQL if recalculate_points else SOURCE_SQL}) TO STDOUT WITH (FORMAT CSV)",
                    (scope.value,),
                ) as copy:
                    async for block in copy:
                        destination.write(block)
    if recalculate_points:
        runs = recalculate_snapshot_points(csv_path, course_tiers)
    elif csv_path.stat().st_size:
        runs = np.atleast_1d(np.loadtxt(csv_path, delimiter=",", dtype=DTYPE))
    else:
        runs = np.empty(0, dtype=DTYPE)
    runs = eligible_runs(runs)
    np.save(path / "runs.npy", runs)
    (path / "maps.json").write_text(json.dumps(metadata_maps) + "\n")
    csv_path.unlink()
    metadata = {
        "version": 1,
        "scope": scope.value,
        "created_at": datetime.now(UTC).isoformat(),
        "players": len(np.unique(runs["player"])),
        "best_map_rows": len(runs),
        "seconds": perf_counter() - start,
        "rating_settings": asdict(get_rank_system_settings().rating),
        "points_source": "recalculated_from_pb_times"
        if recalculate_points
        else "stored_pb_points",
        "points_settings": asdict(get_rank_system_settings().points),
        "sha256": {name: checksum(path / name) for name in ("runs.npy", "maps.json")},
    }
    (path / "metadata.json").write_text(
        json.dumps(metadata, indent=2, default=str) + "\n"
    )
    await async_engine.dispose()
    return metadata


def evaluate_player(
    rows: list[tuple[int, int, int]],
    tiers: dict[int, int],
    skills: dict[int, tuple[Decimal, ...]],
    settings: RatingSettings,
    fields: tuple[str, ...] = FIELDS,
) -> tuple[int, ...]:
    """Use the production calculators on best-per-main-course snapshot rows."""
    result = {}
    if "rating" in fields:
        result["rating"] = calculate_weighted_rating(
            (point for _course, _map, point in rows), settings=settings
        )
    if "rating_easy" in fields:
        easy = [point for course, _map, point in rows if 0 < tiers.get(course, 0) <= 4]
        result["rating_easy"] = calculate_weighted_rating(
            sorted(easy, reverse=True)[: settings.easy_top_maps], settings=settings
        )
    if "rating_hard" in fields:
        hard = [point for course, _map, point in rows if tiers.get(course, 0) >= 5]
        result["rating_hard"] = calculate_weighted_rating(
            sorted(hard, reverse=True)[: settings.hard_top_maps], settings=settings
        )
    for index, skill in enumerate(SKILLS):
        if f"rating_{skill}" in fields:
            result[f"rating_{skill}"] = calculate_skill_rating(
                [
                    (point, skills[map_id][index], map_id)
                    for _course, map_id, point in rows
                    if map_id in skills
                ],
                full_portion_decay=float(settings.skill_full_portion_decay),
                max_full_portion_entries=settings.skill_top_map_equivalents
                / len(SKILLS),
                settings=settings,
            )
    return tuple(result[field] for field in fields)


def evaluate(
    path: Path,
    output: Path,
    settings: RatingSettings,
    fields: tuple[str, ...] = FIELDS,
    *,
    calibrate_converters: bool = False,
    converters_path: Path | None = None,
) -> dict[str, Any]:
    start = perf_counter()
    if output.suffix.lower() != ".csv":
        raise ValueError("Candidate output must use a .csv extension")
    artifacts = {
        path.resolve() / name for name in ("runs.npy", "maps.json", "metadata.json")
    }
    if (
        output.resolve() in artifacts
        or output.with_suffix(".json").resolve() in artifacts
    ):
        raise ValueError("Candidate output must not overwrite snapshot inputs")
    metadata = json.loads((path / "metadata.json").read_text())
    if metadata["version"] != 1:
        raise ValueError("Unsupported snapshot version; extract again")
    if calibrate_converters and (metadata["scope"] != "OVR" or converters_path):
        raise ValueError(
            "Shared converters must be calibrated from OVR, without --converters"
        )
    for name in ("runs.npy", "maps.json"):
        if checksum(path / name) != metadata["sha256"][name]:
            raise ValueError(f"Snapshot checksum mismatch: {name}")
    maps = json.loads((path / "maps.json").read_text())
    tiers = {int(key): value for key, value in maps["tiers"].items()}
    skills = {
        int(key): tuple(Decimal(value) for value in values)
        for key, values in maps["skills"].items()
    }
    runs = np.load(path / "runs.npy", mmap_mode="r", allow_pickle=False)
    players, starts, counts = np.unique(
        runs["player"], return_index=True, return_counts=True
    )
    if len(players) != metadata["players"] or len(runs) != metadata["best_map_rows"]:
        raise ValueError("Incomplete snapshot; extract again")
    ratings = np.empty((len(players), len(fields)), dtype=np.int64)
    for index, (offset, count) in enumerate(zip(starts, counts, strict=True)):
        rows = [
            (int(row["course"]), int(row["map"]), int(row["points"]))
            for row in runs[offset : offset + count]
        ]
        ratings[index] = evaluate_player(rows, tiers, skills, settings, fields)
    output.parent.mkdir(parents=True, exist_ok=True)
    settings_payload = json.loads(json.dumps(asdict(settings), default=str))
    curves: dict[str, Any] | None = None
    if calibrate_converters:
        curves = {
            "version": 1,
            "source_scope": "OVR",
            "sample_size": len(players),
            "snapshot_sha256": metadata["sha256"],
            "rating_settings": settings_payload,
            "metrics": {},
        }
        for index, field in enumerate(fields):
            values, frequencies = np.unique(ratings[:, index], return_counts=True)
            calibration = calibrate(
                [
                    (int(value), int(count))
                    for value, count in zip(values, frequencies, strict=True)
                ],
                max_raw_rating=settings.target_max_raw_rating,
            )
            curves["metrics"][field] = calibration.anchors
        output.with_suffix(".converters.json").write_text(
            json.dumps(curves, indent=2) + "\n"
        )
    elif converters_path:
        curves = json.loads(converters_path.read_text())
        if curves["version"] != 1 or curves["source_scope"] != "OVR":
            raise ValueError("Expected OVR-calibrated shared converters")
        if curves["rating_settings"] != settings_payload:
            raise ValueError(
                "Converter parameters differ from the candidate parameters"
            )
        if any(field not in curves["metrics"] for field in fields):
            raise ValueError("Converters do not cover all selected rating fields")
    with output.open("w", newline="") as destination:
        writer = csv.writer(destination)
        writer.writerow(
            (
                "steamid64",
                *fields,
                *(f"{field}_normalized" for field in fields if curves),
            )
        )
        for index in np.argsort(-ratings[:, 0], kind="stable"):
            normalized = (
                [
                    convert_skill_rating(
                        int(ratings[index, column]), curves["metrics"][field]
                    )
                    for column, field in enumerate(fields)
                ]
                if curves
                else []
            )
            writer.writerow((str(players[index]), *ratings[index], *normalized))
    report = {
        "scope": metadata["scope"],
        "snapshot_created_at": metadata["created_at"],
        "snapshot_sha256": metadata["sha256"],
        "players": len(players),
        "seconds": perf_counter() - start,
        "rating_settings": asdict(settings),
        "fields": fields,
        "converter_source_scope": curves["source_scope"] if curves else None,
        "raw_rating_percentiles": {
            field: np.percentile(ratings[:, index], [0, 50, 90, 99, 100]).tolist()
            if len(players)
            else []
            for index, field in enumerate(fields)
        },
    }
    output.with_suffix(".json").write_text(
        json.dumps(report, indent=2, default=str) + "\n"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("snapshot", "evaluate"))
    parser.add_argument(
        "--scope", choices=[scope.value for scope in ModeScope], default="SKZ"
    )
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--recalculate-points",
        action="store_true",
        help="Snapshot fresh points from complete PB time buckets without writing them to the database.",
    )
    converter_options = parser.add_mutually_exclusive_group()
    converter_options.add_argument(
        "--calibrate-converters",
        action="store_true",
        help="Calibrate shared display curves from this OVR candidate.",
    )
    converter_options.add_argument(
        "--converters", type=Path, help="Reuse an OVR candidate's curves for any scope."
    )
    parser.add_argument(
        "--ratings",
        choices=list(FIELD_GROUPS),
        default="all",
        help="Calculate only the rating categories being tuned.",
    )
    parser.add_argument("--decay", type=Decimal)
    parser.add_argument("--easy-top-maps", type=int)
    parser.add_argument("--hard-top-maps", type=int)
    parser.add_argument("--skill-full-portion-decay", type=Decimal)
    parser.add_argument("--skill-top-map-equivalents", type=int)
    args = parser.parse_args()
    rating = get_rank_system_settings().rating
    overrides = {
        field: getattr(args, field)
        for field in (
            "decay",
            "easy_top_maps",
            "hard_top_maps",
            "skill_full_portion_decay",
            "skill_top_map_equivalents",
        )
        if getattr(args, field) is not None
    }
    rating = replace(rating, **overrides)
    if (
        not rating.decay.is_finite()
        or not rating.skill_full_portion_decay.is_finite()
        or not 0 < rating.decay < 1
        or not 0 < rating.skill_full_portion_decay < 1
    ):
        parser.error("decays must be between zero and one")
    if (
        min(
            rating.easy_top_maps, rating.hard_top_maps, rating.skill_top_map_equivalents
        )
        < 1
    ):
        parser.error("map limits must be positive")
    path = args.snapshot or ROOT / ".temp/rating-tuning" / args.scope.lower()
    if args.action == "snapshot":
        if overrides or args.calibrate_converters or args.converters:
            parser.error("parameter overrides and converters apply only to evaluate")
        result = asyncio.run(
            snapshot(
                path, ModeScope(args.scope), recalculate_points=args.recalculate_points
            )
        )
    else:
        if args.recalculate_points:
            parser.error("--recalculate-points applies only to snapshot")
        if json.loads((path / "metadata.json").read_text())["scope"] != args.scope:
            parser.error("snapshot scope does not match --scope")
        output = (
            args.output
            or ROOT / ".temp/rating-tuning" / f"{args.scope.lower()}-candidate.csv"
        )
        result = evaluate(
            path,
            output,
            rating,
            FIELD_GROUPS[args.ratings],
            calibrate_converters=args.calibrate_converters,
            converters_path=args.converters,
        )
    print(json.dumps(result, indent=2, default=str))  # noqa: T201


if __name__ == "__main__":
    main()
