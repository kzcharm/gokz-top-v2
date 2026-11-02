import pytest

from app.core.config import settings
from app.models.mode_scope import ModeScopeId
from app.services.course_points import calculate_course_pb_points
from app.services.rank_points_candidate import (
    MIN_POINTS_BY_TIER,
    rank_points_candidate,
)


@pytest.mark.parametrize("total", [1, 2, 10, 50, 1000])
def test_candidate_preserves_rank_order_and_unique_wr(total):
    for tier in range(1, 9):
        scores = [
            rank_points_candidate(rank=r, total=total, tier=tier)
            for r in range(1, total + 1)
        ]
        assert scores[0] == 1000
        assert all(1 <= s <= 999 for s in scores[1:])
        assert all(a >= b for a, b in zip(scores, scores[1:], strict=False))


def test_shared_curve_centers_t1_and_rewards_tier_at_equal_percentile():
    assert 499 <= rank_points_candidate(rank=5000, total=10000, tier=1) <= 501
    values = [
        rank_points_candidate(rank=9000, total=10000, tier=t) for t in range(1, 9)
    ]
    assert all(a < b for a, b in zip(values, values[1:], strict=False))
    assert rank_points_candidate(rank=10000, total=10000, tier=6) == 800


@pytest.mark.parametrize("tier,floor", MIN_POINTS_BY_TIER.items())
def test_tier_floors_are_enforced_without_piling_up_at_floor(tier, floor):
    assert rank_points_candidate(rank=1000000, total=1000000, tier=tier) == floor
    assert rank_points_candidate(rank=500, total=1000, tier=tier) > floor


def test_harder_tiers_reward_every_percentile_more():
    for rank in range(2, 1001):
        scores = [
            rank_points_candidate(rank=rank, total=1000, tier=t) for t in range(1, 9)
        ]
        assert all(a <= b for a, b in zip(scores, scores[1:], strict=False))


@pytest.mark.parametrize("tier", range(1, 9))
@pytest.mark.parametrize("rank", [2, 5, 20, 50, 90])
def test_equal_midrank_percentiles_keep_scores_in_smaller_buckets(tier, rank):
    # Multiplying the midrank by an odd factor preserves its exact percentile.
    assert rank_points_candidate(rank=rank, total=100, tier=tier) == (
        rank_points_candidate(rank=5 * rank - 2, total=500, tier=tier)
    )


def test_nine_hundred_threshold_scales_with_bucket_and_tier():
    def count(total, tier):
        return sum(
            rank_points_candidate(rank=r, total=total, tier=tier) >= 900
            for r in range(1, total + 1)
        )

    # No top-100 cutoff. Higher tiers intentionally permit more 900+ scores;
    # smaller buckets still have proportionally fewer qualifying places.
    assert 70 <= count(20000, 1) <= 90
    assert 700 <= count(3500, 6) <= 900
    assert 20 <= count(100, 6) <= 26
    assert count(100, 8) == 100
    assert count(2000, 1) < count(20000, 1)
    assert count(2000, 1) < count(2000, 6)


@pytest.mark.parametrize(
    "rank,total,tier", [(0, 10, 1), (11, 10, 1), (1, 0, 1), (1, 10, 0)]
)
def test_candidate_rejects_invalid_inputs(rank, total, tier):
    with pytest.raises(ValueError):
        rank_points_candidate(rank=rank, total=total, tier=tier)


def test_preview_only_changes_local_ovr_nub_and_ignores_time(monkeypatch):
    args = {"rank": 2, "total": 10, "time_ms": 20000, "wr_time_ms": 10000, "tier": 6}
    monkeypatch.setattr(settings, "LOCAL_OVR_NUB_RANK_POINTS_PREVIEW", False)
    scope_id = ModeScopeId.OVR
    baseline = calculate_course_pb_points(**args, is_pro_only=False, scope_id=scope_id)
    monkeypatch.setattr(settings, "LOCAL_OVR_NUB_RANK_POINTS_PREVIEW", True)
    monkeypatch.setattr(settings, "ENVIRONMENT", "local")
    candidate = rank_points_candidate(rank=2, total=10, tier=6)
    assert (
        calculate_course_pb_points(**args, is_pro_only=False, scope_id=scope_id)
        == candidate
    )
    assert (
        calculate_course_pb_points(
            **(args | {"time_ms": 1000000}), is_pro_only=False, scope_id=scope_id
        )
        == candidate
    )
    for scope in (ModeScopeId.KZT, ModeScopeId.SKZ, ModeScopeId.VNL, None):
        assert (
            calculate_course_pb_points(**args, is_pro_only=False, scope_id=scope)
            == baseline
        )
    assert calculate_course_pb_points(**args, is_pro_only=True, scope_id=scope_id) == 1
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    assert (
        calculate_course_pb_points(**args, is_pro_only=False, scope_id=scope_id)
        == baseline
    )
