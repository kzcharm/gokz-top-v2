import csv
import json
import random
from dataclasses import replace
from decimal import Decimal
from uuid import UUID

import numpy as np
import pytest
from sqlalchemy import update
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.rank_system import get_rank_system_settings
from app.crud.leaderboard_player import PlayerPbRow, _build_leaderboard_values
from app.models import Map, MapSkill, RecordPb, RecordType
from app.services.skill_rating import SKILLS
from scripts.tune_ratings import (
    DTYPE,
    FIELD_GROUPS,
    FIELDS,
    RECALCULATE_SOURCE_SQL,
    SOURCE_SQL,
    checksum,
    eligible_runs,
    evaluate,
    evaluate_player,
    recalculate_snapshot_points,
)
from tests.api.routes.test_leaderboards import _create_ban, _seed_leaderboard_data


@pytest.mark.parametrize("decay", ["0.9", "0.95", "0.975", "0.99", "0.999"])
def test_snapshot_calculation_matches_production(monkeypatch, decay):
    config = replace(
        get_rank_system_settings(),
        rating=replace(
            get_rank_system_settings().rating,
            decay=Decimal(decay),
            easy_top_maps=13,
            hard_top_maps=7,
            skill_full_portion_decay=Decimal(decay),
            skill_top_map_equivalents=19,
            target_max_raw_rating=39000,
        ),
    )
    monkeypatch.setattr(
        "app.crud.leaderboard_player.get_rank_system_settings", lambda: config
    )
    monkeypatch.setattr(
        "app.services.skill_rating.get_rank_system_settings", lambda: config
    )
    rng = random.Random(42)
    for count in (10, 51, 150, 1500):
        source = []
        best = []
        tiers = {}
        skills = {}
        analyses = {}
        for course in range(count):
            nub, pro = rng.randint(1, 1000), rng.randint(1, 1000)
            source.extend(
                [
                    PlayerPbRow(
                        course, course, RecordType.NUB, UUID(int=course * 2), nub
                    ),
                    PlayerPbRow(
                        course, course, RecordType.PRO, UUID(int=course * 2 + 1), pro
                    ),
                ]
            )
            best.append((course, course, max(nub, pro)))
            tiers[course] = course % 9
            if course % 7:
                portions = tuple(
                    Decimal(rng.choice((0, 1, 50, 5000, 10000))) / 10000 for _ in SKILLS
                )
                skills[course] = portions
                analyses[course] = MapSkill(
                    map_id=course,
                    segments=[],
                    **dict(zip(SKILLS, portions, strict=True)),
                )
        expected = _build_leaderboard_values(
            rows=source, tiers_by_course_id=tiers, skills_by_map_id=analyses
        )
        assert evaluate_player(best, tiers, skills, config.rating) == tuple(
            expected[field] for field in FIELDS
        )
        for fields in FIELD_GROUPS.values():
            assert evaluate_player(best, tiers, skills, config.rating, fields) == tuple(
                expected[field] for field in fields
            )


def test_evaluation_preserves_steamids_and_rejects_corruption(tmp_path):
    steamid = 76561199022242128
    runs = np.asarray(
        [(steamid, index, index, 900) for index in range(10)], dtype=DTYPE
    )
    np.save(tmp_path / "runs.npy", runs)
    (tmp_path / "maps.json").write_text(
        json.dumps({"tiers": {str(index): 4 for index in range(10)}, "skills": {}})
    )
    metadata = {
        "version": 1,
        "scope": "SKZ",
        "created_at": "2026-11-02T00:00:00Z",
        "players": 1,
        "best_map_rows": 10,
        "sha256": {
            name: checksum(tmp_path / name) for name in ("runs.npy", "maps.json")
        },
    }
    (tmp_path / "metadata.json").write_text(json.dumps(metadata))
    result = evaluate(
        tmp_path, tmp_path / "candidate.csv", get_rank_system_settings().rating
    )
    assert result["players"] == 1
    assert (
        (tmp_path / "candidate.csv")
        .read_text()
        .splitlines()[1]
        .startswith(f"{steamid},")
    )
    (tmp_path / "maps.json").write_text("{}")
    with pytest.raises(ValueError, match="checksum mismatch"):
        evaluate(
            tmp_path, tmp_path / "candidate.csv", get_rank_system_settings().rating
        )


@pytest.mark.asyncio
async def test_snapshot_source_filters_scope_bans_maps_and_eligibility(
    db: AsyncSession,
):
    players = await _seed_leaderboard_data(db)
    await _create_ban(
        db, ban_id=2120900999, steamid64=players["alpha"], expires_on=None
    )
    await db.exec(update(Map).where(Map.id == 2_120_100_000).values(validated=False))
    connection = await db.connection()
    raw = await connection.get_raw_connection()
    async with raw.driver_connection.cursor() as cursor:
        await cursor.execute(SOURCE_SQL, ("KZT",))
        runs = eligible_runs(np.asarray(await cursor.fetchall(), dtype=DTYPE))
    selected = runs[np.isin(runs["player"], list(players.values()))]
    assert set(selected["player"]) == {players["beta"]}
    assert len(selected) == 19
    assert 2_120_100_000 not in selected["map"]


def test_empty_snapshot_population_and_input_protection(tmp_path):
    assert len(eligible_runs(np.empty(0, dtype=DTYPE))) == 0
    assert (
        len(eligible_runs(np.asarray([(1, i, i, 100) for i in range(9)], dtype=DTYPE)))
        == 0
    )
    with pytest.raises(ValueError, match="overwrite snapshot"):
        evaluate(tmp_path, tmp_path / "maps.csv", get_rank_system_settings().rating)


@pytest.mark.asyncio
async def test_snapshot_recalculates_points_when_database_refresh_is_incomplete(
    db, tmp_path
):
    await _seed_leaderboard_data(db)
    connection = await db.connection()
    raw = await connection.get_raw_connection()
    async with raw.driver_connection.cursor() as cursor:
        await cursor.execute(SOURCE_SQL, ("KZT",))
        expected = np.asarray(await cursor.fetchall(), dtype=DTYPE)
    await db.exec(update(RecordPb).values(points=1))
    async with raw.driver_connection.cursor() as cursor:
        await cursor.execute(RECALCULATE_SOURCE_SQL, ("KZT",))
        source = await cursor.fetchall()
    path = tmp_path / "source.csv"
    with path.open("w", newline="") as destination:
        csv.writer(destination).writerows(source)
    tiers = {str(row[1]): (4 if int(row[2]) < 2_120_100_010 else 5) for row in source}
    actual = recalculate_snapshot_points(path, tiers)
    np.testing.assert_array_equal(actual, expected)


def test_ovr_converter_is_reused_without_recalibrating_other_scopes(tmp_path):
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    runs = np.asarray(
        [
            (player, course, course, player)
            for player in range(1, 1001)
            for course in range(10)
        ],
        dtype=DTYPE,
    )
    np.save(snapshot / "runs.npy", runs)
    (snapshot / "maps.json").write_text(json.dumps({"tiers": {}, "skills": {}}))
    metadata = {
        "version": 1,
        "scope": "OVR",
        "created_at": "2026-11-02T00:00:00Z",
        "players": 1000,
        "best_map_rows": len(runs),
        "sha256": {
            name: checksum(snapshot / name) for name in ("runs.npy", "maps.json")
        },
    }
    (snapshot / "metadata.json").write_text(json.dumps(metadata))
    settings = replace(get_rank_system_settings().rating, decay=Decimal("0.99"))
    evaluate(
        snapshot, tmp_path / "ovr.csv", settings, ("rating",), calibrate_converters=True
    )
    with (tmp_path / "ovr.csv").open() as source:
        expected = {
            row["steamid64"]: row["rating_normalized"] for row in csv.DictReader(source)
        }
    curves = tmp_path / "ovr.converters.json"
    original_curve = curves.read_bytes()
    runs = runs[np.isin(runs["player"], [1, 500, 1000])]
    np.save(snapshot / "runs.npy", runs)
    metadata.update(scope="SKZ", players=3, best_map_rows=len(runs))
    metadata["sha256"]["runs.npy"] = checksum(snapshot / "runs.npy")
    (snapshot / "metadata.json").write_text(json.dumps(metadata))
    evaluate(
        snapshot, tmp_path / "skz.csv", settings, ("rating",), converters_path=curves
    )
    with (tmp_path / "skz.csv").open() as source:
        for row in csv.DictReader(source):
            assert row["rating_normalized"] == expected[row["steamid64"]]
    assert curves.read_bytes() == original_curve
    with pytest.raises(ValueError, match="calibrated from OVR"):
        evaluate(
            snapshot,
            tmp_path / "bad.csv",
            settings,
            ("rating",),
            calibrate_converters=True,
        )
    with pytest.raises(ValueError, match="parameters differ"):
        evaluate(
            snapshot,
            tmp_path / "bad.csv",
            replace(settings, decay=Decimal("0.975")),
            ("rating",),
            converters_path=curves,
        )
