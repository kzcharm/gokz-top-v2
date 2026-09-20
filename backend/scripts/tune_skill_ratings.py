"""Offline, full-OVR virtual-entry rating experiments.

Run from backend/: python scripts/tune_skill_ratings.py snapshot|evaluate|apply.
NumPy is a development-only dependency; the production rating service does not
import this script or NumPy. Snapshot contents live under ../.temp/.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import struct
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from sqlalchemy import text
from sqlmodel import col, select

from app.core.config import settings as app_settings
from app.core.db import async_engine, async_session_maker
from app.core.rank_system import get_rank_system_settings
from app.crud.ban import not_active_ban_exists_split_clause
from app.models import LeaderboardPlayer, Map, MapCourse, MapSkill, ModeScope
from app.services.skill_rating import SKILLS
from app.services.skill_rating_converter import (
    TIED_TOP_DISPLAY_RATING,
    TOP_DISPLAY_RATING,
    calibrate,
)

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / ".temp" / "skill-rating-tuning" / "full-ovr-v1"
DTYPE = np.dtype([("player", "<i4"), ("points", "<u2"), ("map", "<u4")])
SOURCE_DTYPE = np.dtype([("steamid64", "<u8"), ("map", "<u4"), ("points", "<u2")])
COARSE_GRID = (
    0.90,
    0.925,
    0.94,
    0.95,
    0.96,
    0.97,
    0.975,
    0.98,
    0.985,
    0.99,
    0.9925,
    0.995,
)
EXEMPLARS = {
    "xva0": 76561199416019012,
    "Boyo": 76561198093076945,
    "smieszneznaczki": 76561198325578948,
    "Cinyan10": 76561199022242128,
    "LBGDRE": 76561198417871586,
    "kuu": 76561198149087452,
    "FrozeEnd": 76561197963395006,
    "Caster": 76561198365323973,
    "Karri": 76561198286214615,
    "JS_Lzd": 76561198399413724,
    "Rionv1c": 76561198397340143,
    "newbie": 76561198294666994,
}


SOURCE_RUNS_SQL = """
    SELECT rp.steamid64, mc.map_id, MAX(rp.points) AS points
    FROM record_pb AS rp
    JOIN leaderboard_player AS lp
      ON lp.scope = rp.scope AND lp.steamid64 = rp.steamid64
    JOIN map_course AS mc ON mc.id = rp.course_id AND mc.stage = 0
    JOIN map AS m ON m.id = mc.map_id AND m.validated IS TRUE
    JOIN map_skill AS ms ON ms.map_id = m.id
    WHERE rp.scope = 'OVR'::mode_scope
    GROUP BY rp.steamid64, mc.map_id
    ORDER BY rp.steamid64, MAX(rp.points) DESC, mc.map_id
"""


async def _roster_and_maps(
    session: Any,
) -> tuple[list[Any], dict[int, tuple[int, ...]], list[int]]:
    players = (
        await session.execute(
            select(
                col(LeaderboardPlayer.steamid64),
                col(LeaderboardPlayer.unique_map_finishes),
                col(LeaderboardPlayer.records_800_plus),
                col(LeaderboardPlayer.records_900_plus),
                col(LeaderboardPlayer.wrs_nub),
                col(LeaderboardPlayer.wrs_pro),
                not_active_ban_exists_split_clause(
                    steamid64_column=col(LeaderboardPlayer.steamid64)
                ),
            )
            .where(col(LeaderboardPlayer.scope) == ModeScope.OVR)
            .order_by(col(LeaderboardPlayer.steamid64))
        )
    ).all()
    maps = (
        await session.execute(
            select(
                col(MapCourse.id),
                col(MapCourse.map_id),
                *(getattr(MapSkill, skill) for skill in SKILLS),
            )
            .join(Map, col(MapCourse.map_id) == col(Map.id))
            .join(MapSkill, col(MapSkill.map_id) == col(Map.id))
            .where(col(Map.validated).is_(True), col(MapCourse.stage) == 0)
        )
    ).all()
    mapping = {
        int(row[0]): (int(row[1]), *(int(portion * 10000) for portion in row[2:]))
        for row in maps
    }
    return players, mapping, sorted(mapping)


def _metadata_hash(players: list[Any], mapping: dict[int, tuple[int, ...]]) -> str:
    sha = hashlib.sha256()
    for row in players:
        sha.update(json.dumps(tuple(row), separators=(",", ":")).encode())
    for course_id, payload in sorted(mapping.items()):
        sha.update(struct.pack("<II6H", course_id, *payload))
    return sha.hexdigest()


async def _copy_source_csv(connection: Any, path: Path) -> None:
    """Use PostgreSQL COPY instead of awaiting millions of individual rows."""
    if not hasattr(connection, "get_raw_connection"):
        connection = await connection.connection()
    raw_connection = await connection.get_raw_connection()
    driver_connection = raw_connection.driver_connection
    copy_sql = f"COPY ({SOURCE_RUNS_SQL}) TO STDOUT WITH (FORMAT CSV)"
    with path.open("wb") as destination:
        async with driver_connection.cursor().copy(copy_sql) as copy:
            async for block in copy:
                destination.write(block)


def _read_source_csv(path: Path, steamids: np.ndarray) -> np.ndarray:
    source = np.atleast_1d(np.loadtxt(path, delimiter=",", dtype=SOURCE_DTYPE))
    if not len(source):
        return np.empty(0, dtype=DTYPE)
    source_steamids = source["steamid64"].astype(np.int64)
    player_indices = np.searchsorted(steamids, source_steamids)
    if np.any(player_indices == len(steamids)) or np.any(
        steamids[player_indices] != source_steamids
    ):
        raise ValueError("PB stream contains a player outside the OVR roster")
    result = np.empty(len(source), dtype=DTYPE)
    result["player"] = player_indices
    result["points"] = source["points"]
    result["map"] = source["map"]
    return result


async def build_snapshot(path: Path) -> dict[str, Any]:
    path.mkdir(parents=True, exist_ok=True)
    start_time = time.perf_counter()
    async with async_engine.connect() as connection:
        await connection.execute(
            text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        )
        players, mapping, _course_ids = await _roster_and_maps(connection)
        steamids = np.asarray([int(row[0]) for row in players], dtype=np.int64)
        raw_path = path / "runs-extracting.csv"
        await _copy_source_csv(connection, raw_path)
        await connection.rollback()
    source = _read_source_csv(raw_path, steamids)
    size = len(source)
    source_hash = hashlib.sha256(source.tobytes()).hexdigest()
    np.save(path / "runs.npy", source)
    del source
    raw_path.unlink()
    max_map_id = max(value[0] for value in mapping.values())
    portions = np.zeros((max_map_id + 1, len(SKILLS)), dtype=np.uint16)
    for map_id, *skill_values in mapping.values():
        portions[map_id] = skill_values
    np.save(path / "portions.npy", portions)
    np.save(path / "players.npy", steamids)
    np.save(
        path / "attributes.npy",
        np.asarray([tuple(row[1:]) for row in players], dtype=np.int32),
    )
    artifact_sha256 = {
        name: _file_sha256(path / name)
        for name in ("runs.npy", "portions.npy", "players.npy", "attributes.npy")
    }
    metadata = {
        "version": 1,
        "scope": "OVR",
        "created_at": datetime.now(UTC).isoformat(),
        "population": len(players),
        "source_runs_sha256": source_hash,
        "roster_and_map_sha256": _metadata_hash(players, mapping),
        "artifact_sha256": artifact_sha256,
        "analyzed_main_courses": len(mapping),
        "best_player_map_rows": size,
        "snapshot_seconds": round(time.perf_counter() - start_time, 2),
    }
    (path / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    return metadata


def _file_sha256(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            sha.update(chunk)
    return sha.hexdigest()


def _load(
    path: Path,
) -> tuple[dict[str, Any], np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    metadata = json.loads((path / "metadata.json").read_text())
    if metadata["version"] != 1 or metadata["scope"] != "OVR":
        raise ValueError("Unsupported snapshot version or scope; extract again")
    for name, expected in metadata["artifact_sha256"].items():
        if _file_sha256(path / name) != expected:
            raise ValueError(
                f"Snapshot artifact {name} failed its checksum; extract again"
            )
    players = np.load(path / "players.npy", mmap_mode="r")
    attributes = np.load(path / "attributes.npy", mmap_mode="r")
    runs = np.load(path / "runs.npy", mmap_mode="r")
    portions = np.load(path / "portions.npy", mmap_mode="r")
    if len(players) != metadata["population"] or np.any(np.diff(runs["player"]) < 0):
        raise ValueError("Incomplete or unordered snapshot; extract again")
    return metadata, players, attributes, runs, portions


async def _current_input_fingerprints(
    session: Any,
    path: Path,
) -> tuple[str, str, int]:
    """Fingerprint the exact ordered rating inputs before a destructive apply."""
    players, mapping, _course_ids = await _roster_and_maps(session)
    steamids = np.asarray([int(row[0]) for row in players], dtype=np.int64)
    freshness_path = path / "freshness.csv"
    await _copy_source_csv(session, freshness_path)
    source = _read_source_csv(freshness_path, steamids)
    freshness_path.unlink()
    return (
        hashlib.sha256(source.tobytes()).hexdigest(),
        _metadata_hash(players, mapping),
        len(source),
    )


def evaluate_raw(
    runs: np.ndarray,
    portions: np.ndarray,
    population: int,
    decay: float,
    max_full_portion_entries: float | None = None,
) -> np.ndarray:
    if not 0 < decay < 1:
        raise ValueError("Decay must be strictly between zero and one")
    entry_limit = float(
        get_rank_system_settings().rating.skill_top_map_equivalents / len(SKILLS)
        if max_full_portion_entries is None
        else max_full_portion_entries
    )
    if entry_limit <= 0:
        raise ValueError("max_full_portion_entries must be positive")
    results = np.zeros((population, len(SKILLS)), dtype=np.int32)
    if not len(runs):
        return results
    # Chunk on player boundaries: peak workspace stays bounded even for large populations.
    unique_players, starts, counts = np.unique(
        runs["player"], return_index=True, return_counts=True
    )
    log_decay = math.log(decay)
    for offset in range(0, len(unique_players), 2000):
        ids = unique_players[offset : offset + 2000]
        begin = int(starts[offset])
        end = int(starts[offset + len(ids) - 1] + counts[offset + len(ids) - 1])
        subset = runs[begin:end]
        local_starts = starts[offset : offset + len(ids)] - begin
        local_counts = counts[offset : offset + len(ids)]
        pts = subset["points"].astype(np.float64)
        for index in range(len(SKILLS)):
            weights = portions[subset["map"], index].astype(np.float64) / 10000
            cumulative = np.cumsum(weights)
            previous = np.zeros(len(ids), dtype=np.float64)
            previous[1:] = cumulative[local_starts[1:] - 1]
            before = cumulative - weights - np.repeat(previous, local_counts)
            effective = np.minimum(weights, np.maximum(0, entry_limit - before))
            terms = (
                pts
                * np.exp(log_decay * np.minimum(before, entry_limit))
                * -np.expm1(log_decay * effective)
            )
            summed = np.add.reduceat(terms, local_starts)
            results[ids, index] = np.minimum(40000, np.floor(summed * 40)).astype(
                np.int32
            )
    return results


def _ranks(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="stable")
    ordered = values[order]
    _, starts, counts = np.unique(ordered, return_index=True, return_counts=True)
    ranks = np.empty(len(values), dtype=np.float64)
    ranks[order] = np.repeat(starts + (counts - 1) / 2, counts)
    return ranks


def _corr(left: np.ndarray, right: np.ndarray) -> float:
    if len(left) < 2 or np.all(left == left[0]) or np.all(right == right[0]):
        return float("nan")
    return float(np.corrcoef(_ranks(left), _ranks(right))[0, 1])


def _convert_many(values: np.ndarray, anchors: list[list[int | float]]) -> np.ndarray:
    """Vectorized equivalent of convert_skill_rating for tuning diagnostics."""
    converted = np.full(values.shape, np.nan, dtype=np.float64)
    positive = values > 0
    if len(anchors) < 2 or not np.any(positive):
        return converted
    xs = np.asarray([anchor[0] for anchor in anchors], dtype=np.float64)
    ys = np.asarray([anchor[1] for anchor in anchors], dtype=np.float64)
    current = values[positive].astype(np.float64)
    result = np.ones(len(current), dtype=np.float64)
    above = current >= xs[1]
    indices = np.searchsorted(xs, current[above], side="right") - 1
    terminal = indices >= len(xs) - 1
    above_result = np.empty(len(indices), dtype=np.float64)
    above_result[terminal] = ys[-1]
    between = ~terminal
    x0 = xs[indices[between]]
    x1 = xs[indices[between] + 1]
    y0 = ys[indices[between]]
    y1 = ys[indices[between] + 1]
    t = (current[above][between] - x0) / (x1 - x0)
    above_result[between] = y0 + (y1 - y0) * t * t * (3 - 2 * t)
    result[above] = above_result
    converted[positive] = result
    return converted


def report_candidate(
    decay: float, raw: np.ndarray, players: np.ndarray, attributes: np.ndarray
) -> dict[str, Any]:
    start_time = time.perf_counter()
    eligible = attributes[:, 5].astype(bool)
    population = int(eligible.sum())
    complete = attributes[eligible, 0]
    high = (
        attributes[eligible, 1]
        + 2 * attributes[eligible, 2]
        + 3 * (attributes[eligible, 3] + attributes[eligible, 4])
    )
    display = np.full(raw.shape, np.nan)
    skill_reports = {}
    for index, skill in enumerate(SKILLS):
        values = raw[eligible, index]
        distinct, counts = np.unique(values, return_counts=True)
        calibration = (
            calibrate(
                list(zip(distinct.tolist(), counts.tolist(), strict=True)),
                max_raw_rating=40000,
            )
            if np.any(values > 0)
            else None
        )
        anchors = calibration.anchors if calibration else None
        # Exactly reuse the persisted converter, including sparse-tail behavior.
        if anchors is not None:
            display[:, index] = _convert_many(raw[:, index], anchors)
        percentile_values = np.percentile(values, [10, 25, 50, 75, 90, 99])
        p99_raw = int(distinct[np.searchsorted(distinct, percentile_values[-1])])
        top = sorted(
            zip(distinct.tolist(), counts.tolist(), strict=True), reverse=True
        )[:10]
        skill_reports[skill] = {
            "percentiles": percentile_values.astype(int).tolist(),
            "maximum": int(values.max()),
            "zero": int(np.sum(values == 0)),
            "positive": int(np.sum(values > 0)),
            "exact_cap": int(np.sum(values == 40000)),
            "ties": int(sum(count - 1 for count in counts)),
            "upper_tail": {
                "p99_raw": p99_raw,
                "tied_at_p99_raw": int(counts[distinct == p99_raw][0]),
                "tied_at_maximum": int(counts[-1]),
                "top_distinct_raw_counts": top,
            },
            "completion_correlation": round(_corr(values, complete), 4),
            "high_point_correlation": round(_corr(values, high), 4),
            "attainable_levels": []
            if anchors is None
            else sorted(
                {
                    10
                    if level in {TOP_DISPLAY_RATING, TIED_TOP_DISPLAY_RATING}
                    else int(level)
                    for raw_threshold, level in anchors[1:]
                    if raw_threshold <= int(values.max())
                }
            ),
            "anchors": anchors,
        }
    with np.errstate(all="ignore"):
        ranges = np.nanmax(display[eligible], axis=1) - np.nanmin(
            display[eligible], axis=1
        )
    valid = np.isfinite(ranges)
    ranges = ranges[valid]
    examples = {}
    for name, steamid64 in EXEMPLARS.items():
        index = int(np.searchsorted(players, steamid64))
        if index == len(players) or players[index] != steamid64:
            examples[name] = None
            continue
        examples[name] = {
            skill: {
                "raw": int(raw[index, column]),
                "display": None
                if np.isnan(display[index, column])
                else float(display[index, column]),
            }
            for column, skill in enumerate(SKILLS)
        }
    completion_correlations = [_corr(raw[eligible, i], complete) for i in range(6)]
    high_point_correlations = [_corr(raw[eligible, i], high) for i in range(6)]
    cross_skill_matrix = [
        [
            1.0 if i == j else round(_corr(raw[eligible, i], raw[eligible, j]), 4)
            for j in range(6)
        ]
        for i in range(6)
    ]
    cross_skill_values = [
        cross_skill_matrix[i][j] for i in range(6) for j in range(i + 1, 6)
    ]
    metrics = {
        "mean_completion_correlation": round(
            float(np.nanmean(completion_correlations)), 4
        ),
        "mean_high_point_correlation": round(
            float(np.nanmean(high_point_correlations)), 4
        ),
        "mean_cross_skill_correlation": round(float(np.nanmean(cross_skill_values)), 4),
        "cross_skill_correlation_matrix": cross_skill_matrix,
        "median_display_range": round(float(np.median(ranges)), 3),
        "mean_display_range": round(float(np.mean(ranges)), 3),
        "range_at_least_1": round(float(np.mean(ranges >= 1)), 4),
        "range_at_least_2": round(float(np.mean(ranges >= 2)), 4),
    }
    return {
        "decay": decay,
        "population": population,
        "metrics": metrics,
        "skills": skill_reports,
        "examples": examples,
        "diagnostic_seconds": round(time.perf_counter() - start_time, 2),
    }


async def apply_candidate(path: Path, decay: float) -> dict[str, Any]:
    if app_settings.ENVIRONMENT != "local":
        raise ValueError(
            "This tuning command is intentionally restricted to ENVIRONMENT=local"
        )
    settings_decay = float(get_rank_system_settings().rating.skill_full_portion_decay)
    top_map_equivalents = get_rank_system_settings().rating.skill_top_map_equivalents
    entry_limit = top_map_equivalents / len(SKILLS)
    if decay != settings_decay:
        raise ValueError(
            "Applied decay must match backend/rank-system.toml (nightly rebuild would revert it)"
        )
    metadata, players, attributes, runs, portions = _load(path)
    raw = evaluate_raw(runs, portions, len(players), decay, entry_limit)
    start_time = time.perf_counter()
    async with async_session_maker() as session:
        await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
        source_hash, roster_hash, source_count = await _current_input_fingerprints(
            session, path
        )
        if (
            source_hash != metadata["source_runs_sha256"]
            or roster_hash != metadata["roster_and_map_sha256"]
            or source_count != metadata["best_player_map_rows"]
        ):
            raise ValueError(
                "Snapshot is stale: PBs, bans, roster or map analysis changed. Run snapshot again"
            )
        statement = text(
            """UPDATE leaderboard_player AS lp SET
                 rating_boxtech = v.boxtech, rating_strafe = v.strafe,
                 rating_bhop = v.bhop, rating_climb = v.climb,
                 rating_ladder = v.ladder, rating_slide = v.slide,
                 updated_at = now()
               FROM unnest(CAST(:ids AS bigint[]), CAST(:boxtech AS integer[]),
                           CAST(:strafe AS integer[]), CAST(:bhop AS integer[]),
                           CAST(:climb AS integer[]), CAST(:ladder AS integer[]),
                           CAST(:slide AS integer[]))
                    AS v(steamid64, boxtech, strafe, bhop, climb, ladder, slide)
               WHERE lp.scope = 'OVR'::mode_scope AND lp.steamid64 = v.steamid64
                 AND (lp.rating_boxtech, lp.rating_strafe, lp.rating_bhop,
                      lp.rating_climb, lp.rating_ladder, lp.rating_slide)
                     IS DISTINCT FROM
                     (v.boxtech, v.strafe, v.bhop, v.climb, v.ladder, v.slide)"""
        )
        updated = 0
        for start in range(0, len(players), 2000):
            stop = min(start + 2000, len(players))
            batch = raw[start:stop]
            params = {"ids": players[start:stop].tolist()}
            params.update(
                {skill: batch[:, index].tolist() for index, skill in enumerate(SKILLS)}
            )
            result = await session.execute(statement, params)
            updated += int(getattr(result, "rowcount", 0) or 0)
        # Keep six converter rows and the full OVR raw backfill in one transaction.
        from app.models import SkillRatingConverter
        from app.models.utils import get_datetime_utc

        for index, skill in enumerate(SKILLS):
            values = raw[attributes[:, 5].astype(bool), index]
            distinct, counts = np.unique(values, return_counts=True)
            calibration = calibrate(
                list(zip(distinct.tolist(), counts.tolist(), strict=True)),
                max_raw_rating=40000,
            )
            converter = await session.get(SkillRatingConverter, (ModeScope.OVR, skill))
            if converter is None:
                converter = SkillRatingConverter(
                    scope=ModeScope.OVR,
                    skill=skill,
                    anchors=calibration.anchors,
                    sample_size=calibration.population,
                )
            else:
                converter.anchors = calibration.anchors
                converter.sample_size = calibration.population
                converter.updated_at = get_datetime_utc()
            session.add(converter)
        await session.commit()
    return {
        "updated_rows": updated,
        "population": len(players),
        "top_map_equivalents": top_map_equivalents,
        "max_full_portion_entries_per_skill": entry_limit,
        "apply_seconds": round(time.perf_counter() - start_time, 2),
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("snapshot", "evaluate", "apply"))
    parser.add_argument("--snapshot", type=Path, default=SNAPSHOT)
    parser.add_argument("--decay", type=float, default=None)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Also write JSON Lines output (normally below .temp/).",
    )
    args = parser.parse_args()

    output_started = False

    def emit(payload: dict[str, Any]) -> None:
        nonlocal output_started
        line = json.dumps(payload)
        sys.stdout.write(line + "\n")
        sys.stdout.flush()
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            mode = "a" if output_started else "w"
            with args.output.open(mode, encoding="utf-8") as destination:
                destination.write(line + "\n")
            output_started = True

    if args.command == "snapshot":
        emit(await build_snapshot(args.snapshot))
        return
    metadata, players, attributes, runs, portions = _load(args.snapshot)
    emit({"snapshot": metadata})
    top_map_equivalents = get_rank_system_settings().rating.skill_top_map_equivalents
    entry_limit = top_map_equivalents / len(SKILLS)
    decays = (args.decay,) if args.decay is not None else COARSE_GRID
    if args.command == "apply" and args.decay is None:
        parser.error("apply requires an explicit --decay")
    for decay in decays:
        started = time.perf_counter()
        raw = evaluate_raw(runs, portions, len(players), decay, entry_limit)
        report = report_candidate(decay, raw, players, attributes)
        report["top_map_equivalents"] = top_map_equivalents
        report["max_full_portion_entries_per_skill"] = entry_limit
        report["evaluation_seconds"] = round(time.perf_counter() - started, 2)
        emit(report)
    if args.command == "apply":
        emit(await apply_candidate(args.snapshot, args.decay))


if __name__ == "__main__":
    asyncio.run(main())
