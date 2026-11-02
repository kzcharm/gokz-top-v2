import pytest

from app.core.config import settings
from app.models import ModeScope
from app.services.course_points import (
    calculate_course_pb_points,
    exclude_pro_from_local_preview,
)
from app.services.pro_points_candidate import pro_rank_points_candidate
from app.services.rank_points_candidate import MIN_POINTS_BY_TIER, rank_points_candidate


def test_local_pro_preview_requires_selected_course_and_nub_count(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "local")
    monkeypatch.setattr(settings, "LOCAL_OVR_NUB_RANK_POINTS_PREVIEW", True)
    monkeypatch.setattr(settings, "LOCAL_OVR_PRO_RANK_POINTS_PREVIEW", False)
    monkeypatch.setattr(settings, "LOCAL_OVR_PRO_POINTS_PREVIEW_COURSES", [42])
    args = {
        "rank": 2,
        "total": 10,
        "time_ms": 20000,
        "wr_time_ms": 10000,
        "tier": 6,
        "is_pro_only": True,
        "scope_id": ModeScope.OVR.scope_id,
    }
    assert calculate_course_pb_points(**args, course_id=43) == 1
    with pytest.raises(ValueError, match="NUB population"):
        calculate_course_pb_points(**args, course_id=42)
    assert calculate_course_pb_points(**args, course_id=42, nub_finishers=100) == (
        pro_rank_points_candidate(rank=2, pro_finishers=10, nub_finishers=100, tier=6)
    )
    assert not exclude_pro_from_local_preview(
        scope_id=ModeScope.OVR.scope_id, course_id=42
    )
    assert exclude_pro_from_local_preview(scope_id=ModeScope.OVR.scope_id, course_id=43)
    monkeypatch.setattr(settings, "LOCAL_OVR_PRO_RANK_POINTS_PREVIEW", True)
    assert calculate_course_pb_points(**args, course_id=43, nub_finishers=100) == (
        pro_rank_points_candidate(rank=2, pro_finishers=10, nub_finishers=100, tier=6)
    )
    assert not exclude_pro_from_local_preview(
        scope_id=ModeScope.OVR.scope_id, course_id=43
    )
    assert calculate_course_pb_points(**(args | {"tier": 0}), course_id=43) == 1
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    assert calculate_course_pb_points(**args, course_id=42) != 1
    assert not exclude_pro_from_local_preview(
        scope_id=ModeScope.OVR.scope_id, course_id=43
    )


@pytest.mark.parametrize("environment", ["staging", "production"])
@pytest.mark.parametrize("scope", list(ModeScope))
def test_deployed_rank_points_enable_nub_and_pro(monkeypatch, environment, scope):
    monkeypatch.setattr(settings, "ENVIRONMENT", environment)
    monkeypatch.setattr(settings, "RANK_POINTS_ENABLED", True)
    args = {
        "rank": 2,
        "total": 10,
        "time_ms": 20000,
        "wr_time_ms": 10000,
        "tier": 6,
        "scope_id": scope.scope_id,
    }
    assert calculate_course_pb_points(**args, is_pro_only=False) == (
        rank_points_candidate(rank=2, total=10, tier=6)
    )
    with pytest.raises(ValueError, match="NUB population"):
        calculate_course_pb_points(**args, is_pro_only=True)
    assert calculate_course_pb_points(
        **args, is_pro_only=True, nub_finishers=100
    ) == pro_rank_points_candidate(rank=2, pro_finishers=10, nub_finishers=100, tier=6)
    assert not exclude_pro_from_local_preview(scope_id=scope.scope_id, course_id=43)


@pytest.mark.parametrize("tier", range(1, 9))
def test_everyone_finishing_pro_gets_exactly_zero_rarity_bonus(tier: int) -> None:
    for rank in range(1, 101):
        assert pro_rank_points_candidate(
            rank=rank, pro_finishers=100, nub_finishers=100, tier=tier
        ) == rank_points_candidate(rank=rank, total=100, tier=tier)


@pytest.mark.parametrize("tier", range(1, 9))
def test_more_nub_finishers_reward_the_same_pro_rank(tier: int) -> None:
    scores = [
        pro_rank_points_candidate(
            rank=50, pro_finishers=100, nub_finishers=n, tier=tier
        )
        for n in [100, 200, 1000, 10000]
    ]
    assert all(a < b for a, b in zip(scores, scores[1:], strict=False))


def test_small_population_bonus_is_softened() -> None:
    small = pro_rank_points_candidate(
        rank=5, pro_finishers=10, nub_finishers=100, tier=1
    )
    # Equal midrank percentile, same observed 10% PRO share, larger sample.
    large = pro_rank_points_candidate(
        rank=23, pro_finishers=50, nub_finishers=500, tier=1
    )
    assert small < large
    unsmoothed = pro_rank_points_candidate(
        rank=5, pro_finishers=10, nub_finishers=100, tier=1, smoothing_finishers=0
    )
    assert small < unsmoothed


def test_almost_universal_pro_has_only_a_small_bonus_even_at_last_place() -> None:
    baseline = rank_points_candidate(rank=9900, total=9900, tier=1)
    proposed = pro_rank_points_candidate(
        rank=9900, pro_finishers=9900, nub_finishers=10000, tier=1
    )
    assert 0 <= proposed - baseline <= 5


@pytest.mark.parametrize("tier", range(1, 9))
@pytest.mark.parametrize("total", [1, 2, 10, 1000])
def test_scores_keep_rank_order_floor_and_unique_wr(tier: int, total: int) -> None:
    scores = [
        pro_rank_points_candidate(
            rank=r, pro_finishers=total, nub_finishers=total * 100, tier=tier
        )
        for r in range(1, total + 1)
    ]
    assert scores[0] == 1000
    assert all(MIN_POINTS_BY_TIER[tier] <= score <= 999 for score in scores[1:])
    assert all(a >= b for a, b in zip(scores, scores[1:], strict=False))
    assert all(
        score >= rank_points_candidate(rank=r, total=total, tier=tier)
        for r, score in enumerate(scores, 1)
    )


def test_zero_strength_reproduces_pro_rank_only_scores() -> None:
    for rank in range(1, 101):
        assert pro_rank_points_candidate(
            rank=rank, pro_finishers=100, nub_finishers=10000, tier=6, rarity_strength=0
        ) == rank_points_candidate(rank=rank, total=100, tier=6)


@pytest.mark.parametrize(
    "overrides",
    [
        {"pro_finishers": 0},
        {"pro_finishers": 101},
        {"nub_finishers": 0},
        {"rank": 0},
        {"tier": 0},
        {"rarity_strength": -1},
        {"rarity_strength": 2},
        {"rarity_strength": float("nan")},
        {"smoothing_finishers": -1},
        {"smoothing_finishers": float("inf")},
    ],
)
def test_invalid_inputs_are_rejected(overrides: dict[str, int | float]) -> None:
    with pytest.raises(ValueError):
        pro_rank_points_candidate(
            **(
                {"rank": 2, "pro_finishers": 10, "nub_finishers": 100, "tier": 1}
                | overrides
            )
        )
