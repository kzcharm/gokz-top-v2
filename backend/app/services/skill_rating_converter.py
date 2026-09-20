"""Persisted population-calibrated skill rating curves."""

from bisect import bisect_right
from dataclasses import dataclass

TOP_DISPLAY_RATING = 10.99999
TIED_TOP_DISPLAY_RATING = 10.99
RUNNER_UP_DISPLAY_CEILING = 10.994


@dataclass(frozen=True)
class Calibration:
    anchors: list[list[int | float]]
    population: int
    positive: int
    ties: int


def calibrate(histogram: list[tuple[int, int]], *, max_raw_rating: int) -> Calibration:
    """Calibrate levels 2–10 by percentile and the population best near 11."""
    histogram = sorted(histogram)
    population = sum(count for _, count in histogram)
    positive = sum(count for raw, count in histogram if raw > 0)
    ties = sum(max(count - 1, 0) for _, count in histogram)
    if population == 0 or positive == 0:
        raise ValueError("Cannot calibrate a population with no positive ratings")

    below = 0
    anchors: list[list[int | float]] = [[0, 0]]
    for raw, count in histogram:
        if raw > 0:
            reached = max(
                [1]
                + [
                    level
                    for level in range(2, 11)
                    if below * (2 ** (level - 1)) >= population * (2 ** (level - 1) - 1)
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
    raw: int, anchors: list[list[int | float]] | None
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
