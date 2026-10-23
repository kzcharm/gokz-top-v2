"""Run maintenance commands against real scoped records and derived rows."""

from contextlib import asynccontextmanager
from decimal import Decimal

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import (
    KZMode,
    LeaderboardPlayer,
    Map,
    MapCourse,
    MapCourseTier,
    MapSkill,
    ModeScope,
    Player,
    Record,
    RecordPb,
    ServerGlobalapi,
    SkillRatingConverter,
)
from app.tasks.build import pb, points, rating, skill_rating_converters, skill_ratings
from tests.utils.utils import random_steamid64

pytestmark = pytest.mark.asyncio


def use_session(monkeypatch: pytest.MonkeyPatch, db: AsyncSession) -> None:
    @asynccontextmanager
    async def session_factory():
        yield db

    for module in (pb, points, rating, skill_ratings, skill_rating_converters):
        monkeypatch.setattr(module, "async_session_maker", session_factory)


async def test_pb_points_leaderboard_and_skill_builds_are_repeatable(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use_session(monkeypatch, db)
    player_id = random_steamid64()
    db.add(Player(steamid64=player_id, name="Pipeline player"))
    db.add(ServerGlobalapi(id=972351, name="Pipeline server"))
    db.add(Map(id=972351, name="kz_quality_pipeline", validated=True))
    await db.flush()
    course = MapCourse(map_id=972351, stage=0)
    db.add(course)
    await db.flush()
    db.add(MapCourseTier(course_id=course.id, mode=KZMode.KZT, tier=2))
    db.add(
        MapSkill(
            map_id=972351,
            bhop=Decimal("1"),
            climb=Decimal("0"),
            strafe=Decimal("0"),
            ladder=Decimal("0"),
            boxtech=Decimal("0"),
            slide=Decimal("0"),
            segments=[],
        )
    )
    db.add_all(
        [
            Record(
                steamid64=player_id,
                server_id=972351,
                mode=KZMode.KZT,
                map_id=972351,
                time=Decimal("10"),
                teleports=0,
            ),
            Record(
                steamid64=player_id,
                server_id=972351,
                mode=KZMode.KZT,
                map_id=972351,
                time=Decimal("11"),
                teleports=1,
            ),
        ]
    )
    await db.flush()
    assert points.resolve_scopes(None) == tuple(ModeScope)
    assert points.resolve_scopes(["KZT"]) == (ModeScope.KZT,)
    assert points.resolve_stage(stage=None, all_stages=False) == 0
    assert points.resolve_stage(stage=None, all_stages=True) is None
    assert points.resolve_stage(stage=1, all_stages=False) == 1
    assert rating.resolve_scope_ids([" kzt "]) == [1]
    assert rating.resolve_scope_ids(None) is None
    assert await points._load_course_scope_tiers(courses=[], scopes=[]) == {}
    initial_plan = await pb.list_record_pb_buckets(force_all=True)
    assert initial_plan
    assert all(bucket.scope_name in {"OVR", "KZT"} for bucket in initial_plan)
    assert "PRO" in pb.format_bucket_plan(buckets=initial_plan)
    assert "No record_pb buckets" in pb.format_bucket_plan(buckets=[])
    pb.print_bucket_plan(buckets=initial_plan)
    assert all(item.label for item in pb._build_course_plan(buckets=initial_plan))
    first = await pb.rebuild_record_pbs(
        force_all=False, limit=1, analyze=True, ensure_map_courses=True
    )
    assert first.course_count == 1 and first.row_count == 4
    assert first.ensured_map_courses
    again = await pb.rebuild_record_pbs(
        force_all=True, limit=None, analyze=False, ensure_map_courses=False
    )
    assert again.row_count == first.row_count and not again.ensured_map_courses
    assert (
        len(
            (
                await db.exec(select(RecordPb).where(RecordPb.steamid64 == player_id))
            ).all()
        )
        == 4
    )
    count = await points.rebuild_record_pb_points(
        scopes=[ModeScope.OVR, ModeScope.KZT],
        map_names=["kz_quality_pipeline"],
        stage=0,
        limit=1,
    )
    assert count >= 0
    assert (
        await points.rebuild_record_pb_points(
            scopes=[ModeScope.OVR],
            map_names=["kz_no_such_pipeline"],
            stage=0,
            limit=None,
        )
        == 0
    )
    # Eligibility requires ten distinct validated main maps.
    for index in range(9):
        db.add(
            Map(id=972360 + index, name=f"kz_quality_pipeline_{index}", validated=True)
        )
    await db.flush()
    for index in range(9):
        db.add(
            Record(
                steamid64=player_id,
                server_id=972351,
                mode=KZMode.KZT,
                map_id=972360 + index,
                time=Decimal("10"),
                teleports=0,
            )
        )
    await db.flush()
    await pb.rebuild_record_pbs(
        force_all=True, limit=None, analyze=False, ensure_map_courses=True
    )
    rebuilt = await rating.rebuild_leaderboard_rows(
        scope_ids=[0], steamid64s=[player_id], limit=1
    )
    assert rebuilt.selected == 1 and rebuilt.created == 1
    again_rating = await rating.rebuild_leaderboard_rows(
        scope_ids=[0], steamid64s=[player_id], limit=None
    )
    assert again_rating.selected == 1 and again_rating.updated == 0
    empty = await rating.rebuild_leaderboard_rows(
        scope_ids=[0], steamid64s=[random_steamid64()], limit=1
    )
    assert empty.selected == 0
    row = (
        await db.exec(
            select(LeaderboardPlayer).where(LeaderboardPlayer.steamid64 == player_id)
        )
    ).one()
    row.rating_bhop = 0
    await db.flush()
    changed = await skill_ratings.rebuild_all_skill_ratings(
        scopes=[ModeScope.OVR], limit=1
    )
    assert changed == {ModeScope.OVR: 1}
    assert row.rating_bhop > 0
    assert await skill_ratings.rebuild_all_skill_ratings(
        scopes=[ModeScope.OVR], limit=1
    ) == {ModeScope.OVR: 0}
    calibration = await skill_rating_converters.calibrate_skill_converters(
        scopes=(ModeScope.OVR,), save=False
    )
    assert len(calibration) == 6
    saved = await skill_rating_converters.calibrate_skill_converters(
        scopes=(ModeScope.OVR,), save=True
    )
    assert any(result.calibration is not None for result in saved)
    await skill_rating_converters.calibrate_skill_converters(
        scopes=(ModeScope.OVR,), save=True
    )
    difficulty_preview = await skill_rating_converters.calibrate_difficulty_converters(
        scopes=(ModeScope.OVR,), save=False
    )
    assert [item.skill for item in difficulty_preview] == ["easy", "hard"]
    assert await db.get(SkillRatingConverter, (ModeScope.OVR, "easy")) is None
    await skill_rating_converters.calibrate_difficulty_converters(
        scopes=(ModeScope.OVR,), save=True
    )
    assert await db.get(SkillRatingConverter, (ModeScope.OVR, "easy")) is not None
    assert (
        len(
            await skill_rating_converters.calibrate_skill_converters(
                scopes=(ModeScope.OVR,)
            )
        )
        == 6
    )
    with pytest.raises(ValueError, match="at least one scope"):
        await rating.rebuild_ratings(
            scope_ids=None, scopes=None, steamid64s=None, limit=None, full=True
        )
