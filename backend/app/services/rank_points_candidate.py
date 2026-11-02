"""Experimental rank-only points model, enabled only by the local preview flag."""

from statistics import NormalDist

# Trial parameters, not fitted completion probabilities. Each tier uses a
# normal distribution centered at 500, truncated at its floor and at 999.
MIN_POINTS_BY_TIER = {1: 1, 2: 250, 3: 400, 4: 550, 5: 700, 6: 800, 7: 875, 8: 950}
SIGMA_BY_TIER = {1: 150, 2: 155, 3: 160, 4: 165, 5: 170, 6: 180, 7: 190, 8: 200}
REFERENCES = {
    tier: NormalDist(mu=500, sigma=sigma) for tier, sigma in SIGMA_BY_TIER.items()
}
CDF_BOUNDS = {
    tier: (reference.cdf(MIN_POINTS_BY_TIER[tier]), reference.cdf(999))
    for tier, reference in REFERENCES.items()
}
RANK_BONUS_SHARE = 0.01
RANK_BONUS_WEIGHT = 0.125


def rank_points_candidate(*, rank: int, total: int, tier: int) -> int:
    """Map a within-map midrank into its tier's truncated normal distribution.

    A bonus from remaining headroom tapers linearly across the top 1% of each
    bucket. Both base points and bonus therefore scale with population rather
    than a fixed qualifying rank. WR retains 1000; other ranks cannot become WR
    by rounding. There is no runtime, WR-gap, or scope-wide population input.
    """
    if total < 1 or not 1 <= rank <= total or tier not in REFERENCES:
        raise ValueError("Expected a valid rank, population, and tier 1–8")
    if rank == 1:
        return 1000
    top_fraction = (rank - 0.5) / total
    low_cdf, high_cdf = CDF_BOUNDS[tier]
    base = REFERENCES[tier].inv_cdf(high_cdf - (high_cdf - low_cdf) * top_fraction)
    bonus_portion = max(0.0, 1 - top_fraction / RANK_BONUS_SHARE)
    bonus = (1000 - base) * RANK_BONUS_WEIGHT * bonus_portion
    return min(999, max(MIN_POINTS_BY_TIER[tier], int(base + bonus)))
