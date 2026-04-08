import uuid

import pytest

from app.services.course_points import (
    CoursePbEntry,
    calculate_bucket_points,
    calculate_dist_points_portion,
    calculate_fallback_dist_points_portion,
    calculate_min_points,
    calculate_rank_points_portion,
)


def test_calculate_min_points_uses_spec_table() -> None:
    assert calculate_min_points(tier=1, is_pro_only=False) == 1
    assert calculate_min_points(tier=1, is_pro_only=True) == 1
    assert calculate_min_points(tier=4, is_pro_only=False) == 400
    assert calculate_min_points(tier=4, is_pro_only=True) == 400
    assert calculate_min_points(tier=8, is_pro_only=False) == 970
    assert calculate_min_points(tier=8, is_pro_only=True) == 970


@pytest.mark.parametrize(
    ("rank", "expected"),
    [
        (120, 0.0),
        (100, 0.004),
        (80, 0.084),
        (15, 0.464),
        (2, 0.896),
        (1, 1.0),
    ],
)
def test_calculate_rank_points_portion_matches_spec_examples(
    rank: int,
    expected: float,
) -> None:
    assert calculate_rank_points_portion(rank=rank) == pytest.approx(expected)


def test_calculate_dist_points_portion_uses_percentile_for_large_buckets() -> None:
    assert calculate_dist_points_portion(
        rank=1,
        total=100,
        time_ms=10_000,
        wr_time_ms=10_000,
        tier=4,
    ) == pytest.approx(1.0)
    assert calculate_dist_points_portion(
        rank=50,
        total=100,
        time_ms=12_000,
        wr_time_ms=10_000,
        tier=4,
    ) == pytest.approx(0.51)


def test_calculate_fallback_dist_points_portion_is_monotonic() -> None:
    fastest = calculate_fallback_dist_points_portion(
        time_ms=10_000,
        wr_time_ms=10_000,
        tier=4,
    )
    slower = calculate_fallback_dist_points_portion(
        time_ms=16_000,
        wr_time_ms=10_000,
        tier=4,
    )

    assert fastest == pytest.approx(1.0)
    assert 0.0 < slower < fastest


def test_calculate_fallback_dist_points_portion_handles_extreme_outliers() -> None:
    portion = calculate_fallback_dist_points_portion(
        time_ms=10_000_000_000,
        wr_time_ms=1,
        tier=1,
    )

    assert portion == pytest.approx(0.0)


def test_calculate_bucket_points_clamps_to_public_range() -> None:
    leader_uuid = uuid.uuid4()
    trailing_uuid = uuid.uuid4()
    points = calculate_bucket_points(
        entries=[
            CoursePbEntry(record_uuid=leader_uuid, time_ms=10_000),
            CoursePbEntry(record_uuid=trailing_uuid, time_ms=500_000),
        ],
        tier=1,
        is_pro_only=False,
    )

    assert points[leader_uuid] == 1000
    assert 1 <= points[trailing_uuid] <= 1000
