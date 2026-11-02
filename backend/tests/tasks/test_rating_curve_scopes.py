import pytest

from app.core.config import settings
from app.crud.leaderboard_player import _load_skill_converters
from app.models import ModeScope, SkillRatingConverter
from app.services.course_points import calculate_course_pb_points
from app.services.pro_points_candidate import pro_rank_points_candidate
from app.services.rank_points_candidate import rank_points_candidate
from app.tasks.build import skill_rating_converters


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", list(ModeScope))
async def test_all_eight_display_curves_follow_the_scope_policy(db, scope):
    metrics = ("easy", "hard", "boxtech", "strafe", "bhop", "climb", "ladder", "slide")
    for source, level in (
        (ModeScope.OVR, 2),
        (ModeScope.KZT, 3),
        (ModeScope.SKZ, 4),
        (ModeScope.VNL, 5),
    ):
        for metric in metrics:
            db.add(
                SkillRatingConverter(
                    scope=source,
                    skill=metric,
                    anchors=[[0, 0], [100, level]],
                    sample_size=100,
                )
            )
    await db.flush()
    curves = await _load_skill_converters(session=db, scope=scope)
    assert set(curves) == set(metrics)
    assert all(
        a == [[0, 0], [100, 5 if scope == ModeScope.VNL else 2]]
        for a in curves.values()
    )


@pytest.mark.asyncio
async def test_calibration_deduplicates_shared_scopes(monkeypatch):
    calls = []

    async def capture(**kwargs):
        calls.append(kwargs)
        return []

    monkeypatch.setattr(skill_rating_converters, "_calibrate_converters", capture)
    for build in (
        skill_rating_converters.calibrate_skill_converters,
        skill_rating_converters.calibrate_difficulty_converters,
    ):
        await build(scopes=tuple(ModeScope), save=True)
        assert calls[-1]["scopes"] == (ModeScope.OVR, ModeScope.VNL)
        await build(scopes=(ModeScope.KZT, ModeScope.SKZ))
        assert calls[-1]["scopes"] == (ModeScope.OVR,)


@pytest.mark.parametrize("scope", list(ModeScope))
def test_new_points_use_the_selected_scope_population(monkeypatch, scope):
    monkeypatch.setattr(settings, "ENVIRONMENT", "local")
    monkeypatch.setattr(settings, "LOCAL_RANK_POINTS_PREVIEW_SCOPES", [scope.value])
    args = {
        "rank": 5,
        "total": 10,
        "time_ms": 20000,
        "wr_time_ms": 10000,
        "tier": 6,
        "scope_id": scope.scope_id,
    }
    assert calculate_course_pb_points(
        **args, is_pro_only=False
    ) == rank_points_candidate(rank=5, total=10, tier=6)
    for nub in (10, 100, 1000):
        assert calculate_course_pb_points(
            **args, is_pro_only=True, nub_finishers=nub
        ) == pro_rank_points_candidate(
            rank=5, pro_finishers=10, nub_finishers=nub, tier=6
        )
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    assert calculate_course_pb_points(**args, is_pro_only=True) > 0
