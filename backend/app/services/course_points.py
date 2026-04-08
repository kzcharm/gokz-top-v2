import math
import uuid
from dataclasses import dataclass
from typing import Final

MIN_POINTS_BY_TIER: Final[dict[int, int]] = {
    1: 1,
    2: 50,
    3: 200,
    4: 400,
    5: 600,
    6: 800,
    7: 900,
    8: 970,
}

TOP_FIVE_BONUSES: Final[dict[int, float]] = {
    5: 0.02,
    4: 0.06,
    3: 0.09,
    2: 0.12,
    1: 0.20,
}

DIST_FALLBACK_THRESHOLD: Final[int] = 50


@dataclass(frozen=True, slots=True)
class CoursePbEntry:
    record_uuid: uuid.UUID
    time_ms: int


def calculate_min_points(*, tier: int, is_pro_only: bool) -> int:
    del is_pro_only
    normalized_tier = min(max(tier, 1), 8)
    return MIN_POINTS_BY_TIER[normalized_tier]


def calculate_rank_points_portion(*, rank: int) -> float:
    if rank > 100:
        return 0.0

    portion = 0.004 * (100 - rank + 1)
    if rank <= 20:
        portion += 0.02 * (20 - rank + 1)
    portion += TOP_FIVE_BONUSES.get(rank, 0.0)
    return min(max(portion, 0.0), 1.0)


def calculate_percentile_dist_points_portion(*, rank: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return min(max((total - rank + 1) / total, 0.0), 1.0)


def calculate_fallback_dist_points_portion(
    *,
    time_ms: int,
    wr_time_ms: int,
    tier: int,
) -> float:
    if wr_time_ms <= 0:
        return 0.0

    scale = 2.1 - 0.25 * min(max(tier, 1), 8)
    time_ratio = time_ms / wr_time_ms
    numerator = 1 + math.exp(scale * -0.5)
    exponent = scale * (time_ratio - 1.5)

    # Keep the logistic-style fallback stable for pathological outliers whose
    # time ratios would otherwise overflow exp() on the denominator side.
    if exponent >= 0:
        exp_neg_exponent = math.exp(-exponent) if math.isfinite(exponent) else 0.0
        portion = numerator * exp_neg_exponent / (1 + exp_neg_exponent)
        return min(max(portion, 0.0), 1.0)

    denominator = 1 + math.exp(exponent)
    if denominator == 0:
        return 0.0
    return min(max(numerator / denominator, 0.0), 1.0)


def calculate_dist_points_portion(
    *,
    rank: int,
    total: int,
    time_ms: int,
    wr_time_ms: int,
    tier: int,
) -> float:
    if total >= DIST_FALLBACK_THRESHOLD:
        return calculate_percentile_dist_points_portion(rank=rank, total=total)
    return calculate_fallback_dist_points_portion(
        time_ms=time_ms,
        wr_time_ms=wr_time_ms,
        tier=tier,
    )


def calculate_course_pb_points(
    *,
    rank: int,
    total: int,
    time_ms: int,
    wr_time_ms: int,
    tier: int,
    is_pro_only: bool,
) -> int:
    min_points = calculate_min_points(tier=tier, is_pro_only=is_pro_only)
    rank_portion = calculate_rank_points_portion(rank=rank)
    dist_portion = calculate_dist_points_portion(
        rank=rank,
        total=total,
        time_ms=time_ms,
        wr_time_ms=wr_time_ms,
        tier=tier,
    )
    points = min_points + (1000 - min_points) * (
        0.125 * rank_portion + 0.875 * dist_portion
    )
    return min(max(int(points), 1), 1000)


def calculate_bucket_points(
    *,
    entries: list[CoursePbEntry],
    tier: int,
    is_pro_only: bool,
) -> dict[uuid.UUID, int]:
    if not entries:
        return {}

    wr_time_ms = entries[0].time_ms
    total = len(entries)
    return {
        entry.record_uuid: calculate_course_pb_points(
            rank=index,
            total=total,
            time_ms=entry.time_ms,
            wr_time_ms=wr_time_ms,
            tier=tier,
            is_pro_only=is_pro_only,
        )
        for index, entry in enumerate(entries, start=1)
    }


def calculate_estimated_pb_points(
    *,
    winner_record_uuid: uuid.UUID,
    entries: list[CoursePbEntry],
    tier: int,
    is_pro_only: bool,
) -> int:
    return calculate_bucket_points(
        entries=entries,
        tier=tier,
        is_pro_only=is_pro_only,
    )[winner_record_uuid]
