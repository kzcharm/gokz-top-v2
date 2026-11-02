"""Persisted population-calibrated skill rating curves."""

from bisect import bisect_right
from dataclasses import dataclass
from math import isfinite

TOP_DISPLAY_RATING = 10.99999
TIED_TOP_DISPLAY_RATING = 10.99
RUNNER_UP_DISPLAY_CEILING = 10.994


@dataclass(frozen=True)
class Calibration:
    anchors: list[list[int | float]]
    population: int
    positive: int
    ties: int


def calibrate(
    histogram: list[tuple[int, int]],
    *,
    max_raw_rating: int,
    tail_multiplier: float = 1.7,
) -> Calibration:
    """Preserve levels through eight, then steepen the last two thresholds.

    Levels 2–8 halve the qualifying tail. Above eight, interpolate the extra
    rarity geometrically: level 9 uses sqrt(tail_multiplier), level 10 uses
    tail_multiplier. The default puts level 10 at top 1/870.4 while preserving
    the original lower thresholds. A multiplier of one restores the old curve.
    """
    if not isfinite(tail_multiplier) or tail_multiplier < 1:
        raise ValueError("tail_multiplier must be finite and at least one")
    histogram = sorted(histogram)
    population = sum(count for _, count in histogram)
    positive = sum(count for raw, count in histogram if raw > 0)
    ties = sum(max(count - 1, 0) for _, count in histogram)
    if population == 0 or positive == 0:
        raise ValueError("Cannot calibrate a population with no positive ratings")

    level_divisors = [
        (level, 2 ** (level - 1) * tail_multiplier ** (max(0, level - 8) / 2))
        for level in range(2, 11)
    ]
    below = 0
    anchors: list[list[int | float]] = [[0, 0]]
    for raw, count in histogram:
        if raw > 0:
            reached = max(
                [1]
                + [
                    level
                    for level, divisor in level_divisors
                    if (population - below) * divisor <= population
                ]
            )
            if reached > anchors[-1][1]:
                anchors.append([raw, reached])
        below += count
    observed_maximum = histogram[-1][0]
    if observed_maximum > max_raw_rating:
        raise ValueError("Observed rating exceeds the configured raw-rating maximum")
    if anchors[-1][1] == 10:
        # A tie for first is not strictly better than every other player.
        if histogram[-1][1] != 1:
            if anchors[-1][0] == observed_maximum:
                anchors[-1][1] = TIED_TOP_DISPLAY_RATING
            else:
                anchors.append([observed_maximum, TIED_TOP_DISPLAY_RATING])
        else:
            if observed_maximum - anchors[-1][0] > 1:
                # Keep the runner-up's converter output below the unique maximum.
                anchors.append([observed_maximum - 1, RUNNER_UP_DISPLAY_CEILING])
            if anchors[-1][0] == observed_maximum:
                anchors[-1][1] = TOP_DISPLAY_RATING
            else:
                anchors.append([observed_maximum, TOP_DISPLAY_RATING])
    return Calibration(anchors, population, positive, ties)


def convert_skill_rating(
    raw: int | float, anchors: list[list[int | float]] | None
) -> float | None:
    if raw <= 0 or not anchors or len(anchors) < 2:
        return None
    if raw < anchors[1][0]:
        return 1.0
    xs = [anchor[0] for anchor in anchors]
    index = bisect_right(xs, raw) - 1
    if index >= len(anchors) - 1:
        return float(anchors[-1][1])
    x0, y0 = anchors[index]
    x1, y1 = anchors[index + 1]
    t = (raw - x0) / (x1 - x0)
    smooth = t * t * (3 - 2 * t)
    return y0 + (y1 - y0) * smooth
