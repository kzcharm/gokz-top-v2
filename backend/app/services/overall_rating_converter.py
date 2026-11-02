"""Spread the shared overall 10+ curve by OVR population position."""

from collections import Counter
from math import exp, isfinite, log

from app.services.skill_rating_converter import Calibration, calibrate


def calibrate_overall_rating(
    histogram: list[tuple[float, int]],
    *,
    max_raw_rating: int,
    lower_anchors: list[list[int | float]] | None = None,
    tail_exponent: float = 1 / 3,
) -> Calibration:
    """Preserve the lower curve and spread the 10+ tail by population position.

    The lowest qualifying position starts at 10 and a unique leader reaches
    10.99. Equal raw values share the lower position of their tied group, so
    ties are never split. Saved anchors are reused by every scope; reads do
    not calculate ranks or recalibrate the curve. A cube-root tail gives the
    strongest results extra display space. A smooth middle lift places about
    29% of the 10+ population above 10.50 without compressing the final interval.
    Logarithmic headroom anchors fill
    the final interval so other scopes' near-ceiling results remain distinct.
    """
    if not isfinite(tail_exponent) or not 0 < tail_exponent <= 1:
        raise ValueError("tail_exponent must be between zero and one")
    counts: Counter[float] = Counter()
    for raw, count in histogram:
        if not isfinite(raw) or not 0 <= raw <= max_raw_rating or count <= 0:
            raise ValueError("Expected finite, in-range ratings and positive counts")
        counts[raw] += count
    integer_counts: Counter[int] = Counter()
    for raw, count in counts.items():
        integer_counts[int(raw)] += count
    baseline = calibrate(sorted(integer_counts.items()), max_raw_rating=max_raw_rating)
    anchors = [
        list(anchor)
        for anchor in (lower_anchors if lower_anchors is not None else baseline.anchors)
        if anchor[1] <= 10
    ]
    if lower_anchors is None and anchors[-1][1] < 10:
        threshold = next((raw for raw, level in baseline.anchors if level >= 10), None)
        if threshold is not None:
            anchors.append([threshold, 10])
    population = sum(counts.values())
    positive = sum(count for raw, count in counts.items() if raw > 0)
    ties = sum(count - 1 for count in counts.values())
    if not anchors or anchors[-1][1] != 10:
        # Keep sparse populations' unattainable levels unattainable.
        return Calibration(anchors, population, positive, ties)
    threshold = anchors[-1][0]
    tail = sorted((raw, count) for raw, count in counts.items() if raw >= threshold)
    tail_size = sum(count for _, count in tail)
    # Preserve endpoints and the wider final interval. Scale the lift down for
    # very small exponents so the curve stays monotone for every supported tune.
    tail_lift = 0.8 * min(1, 3 * tail_exponent)
    below = 0
    for raw, count in tail:
        position = below / max(1, tail_size - 1)
        display = round(
            10
            + 0.99 * (1 - (1 - position) ** tail_exponent)
            + tail_lift * position * (1 - position),
            6,
        )
        if raw > threshold:
            anchors.append([raw, display])
        below += count
    if len(tail) >= 2 and tail[-1][1] == 1:
        x0, y0 = anchors[-2]
        x1, y1 = anchors[-1]
        h0 = max(max_raw_rating - x0, 0.000001)
        h1 = max(max_raw_rating - x1, 0.000001)
        if h0 > h1:
            # Save intermediate points rather than requiring a special display
            # formula or rank lookup. Quantize x to the database's fixed grid.
            logarithmic_span = log(h0 / h1)
            extra: dict[float, float] = {}
            for step in range(1, 64):
                raw = round(max_raw_rating - h0 * exp(-logarithmic_span * step / 64), 6)
                if x0 < raw < x1:
                    position = (
                        log(h0 / max(max_raw_rating - raw, 0.000001)) / logarithmic_span
                    )
                    extra[raw] = round(y0 + (y1 - y0) * position, 6)
            anchors[-1:-1] = [[raw, value] for raw, value in sorted(extra.items())]
    return Calibration(anchors, population, positive, ties)
