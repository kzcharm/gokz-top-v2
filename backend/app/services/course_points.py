import math
import uuid
from dataclasses import dataclass

from app.core.rank_system import get_rank_system_settings


@dataclass(frozen=True, slots=True)
class CoursePbEntry:
    record_uuid: uuid.UUID
    time_ms: int


def calculate_min_points(*, tier: int, is_pro_only: bool) -> int:
    del is_pro_only
    normalized_tier = min(max(tier, 1), 8)
    return get_rank_system_settings().points.shared_min_points_by_tier[normalized_tier]


def calculate_rank_points_portion(*, rank: int) -> float:
    settings = get_rank_system_settings().points
    if rank > 100:
        return 0.0

    portion = settings.top_100_increment * (100 - rank + 1)
    if rank <= 20:
        portion += settings.top_20_increment * (20 - rank + 1)
    portion += settings.top_five_bonuses.get(rank, 0.0)
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
    settings = get_rank_system_settings().points
    if wr_time_ms <= 0:
        return 0.0

    scale = settings.dist_fallback_base - (
        settings.dist_fallback_tier_scale * min(max(tier, 1), 8)
    )
    time_ratio = time_ms / wr_time_ms
    numerator = 1 + math.exp(scale * -0.5)
    exponent = scale * (time_ratio - settings.dist_fallback_center)

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
    if total >= get_rank_system_settings().points.dist_fallback_threshold:
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
    rank_system_settings = get_rank_system_settings()
    settings = rank_system_settings.points
    max_map_points = rank_system_settings.rating.max_map_points
    min_points = calculate_min_points(tier=tier, is_pro_only=is_pro_only)
    rank_portion = calculate_rank_points_portion(rank=rank)
    dist_portion = calculate_dist_points_portion(
        rank=rank,
        total=total,
        time_ms=time_ms,
        wr_time_ms=wr_time_ms,
        tier=tier,
    )
    points = min_points + (max_map_points - min_points) * (
        settings.rank_weight * rank_portion + settings.dist_weight * dist_portion
    )
    return min(max(int(points), 1), max_map_points)


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
