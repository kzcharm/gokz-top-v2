"""Moderate PRO rarity rewards for opt-in local scope previews."""

from math import floor, isfinite

from app.services.rank_points_candidate import rank_points_candidate

PRO_RARITY_STRENGTH = 0.5
PRO_SMOOTHING_FINISHERS = 20.0


def pro_rank_points_candidate(
    *,
    rank: int,
    pro_finishers: int,
    nub_finishers: int,
    tier: int,
    rarity_strength: float = PRO_RARITY_STRENGTH,
    smoothing_finishers: float = PRO_SMOOTHING_FINISHERS,
) -> int:
    """Reward rare PRO finishes through the upper tail of the NUB tier curve.

    Inputs count unique, eligible finishers in one scope and course. NUB must
    include every PRO player. A prior favoring PRO completion tempers bonuses
    on thin samples; it preserves an exact zero bonus when every finisher is
    PRO. Square-root rarity gives partial credit by default, instead of
    assuming every PRO finisher belongs above every non-PRO finisher.

    The lift cannot consume more than (1 - retained_tail) of the remaining
    point headroom. This prevents a tiny rarity difference on nearly all-PRO
    maps from creating a large bonus at the extreme bottom of a normal curve.
    WR remains 1000, and other ranks stay below 1000. No time ratio is used.
    """
    if not 1 <= pro_finishers <= nub_finishers:
        raise ValueError("Expected positive PRO finishers within the NUB population")
    if not isfinite(rarity_strength) or not 0 <= rarity_strength <= 1:
        raise ValueError("rarity_strength must be finite and between zero and one")
    if not isfinite(smoothing_finishers) or smoothing_finishers < 0:
        raise ValueError("smoothing_finishers must be finite and non-negative")
    pro_share = (pro_finishers + smoothing_finishers) / (
        nub_finishers + smoothing_finishers
    )
    retained_tail: float = pro_share**rarity_strength
    proposed = rank_points_candidate(
        rank=rank,
        total=pro_finishers,
        tier=tier,
        tail_share=retained_tail,
    )
    baseline = rank_points_candidate(rank=rank, total=pro_finishers, tier=tier)
    bonus_ceiling = floor(baseline + (1000 - baseline) * (1 - retained_tail))
    return min(proposed, bonus_ceiling)
