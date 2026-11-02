from decimal import ROUND_DOWN, Decimal
from math import floor

import pytest

from app.crud.leaderboard_player import calculate_overall_rating
from app.services.overall_rating_converter import calibrate_overall_rating
from app.services.skill_rating_converter import convert_skill_rating


def test_six_decimal_ratings_distinguish_near_ceiling_results():
    values = [calculate_overall_rating([1000] * count) for count in (210, 220)]
    assert int(values[0]) == int(values[1]) == 39999
    assert values[0] < values[1]
    for count, actual in zip((210, 220), values, strict=True):
        expected = (Decimal(40000) * (1 - Decimal("0.95") ** count)).quantize(
            Decimal("0.000001"), rounding=ROUND_DOWN
        )
        assert Decimal(str(actual)) == expected
    assert calculate_overall_rating([]) == 0


def test_saved_tail_curve_spreads_clustered_ratings_and_preserves_lower_curve():
    lower = [[0, 0], [100, 1], [35000, 8], [38000, 9], [39000, 10]]
    histogram = [(0.0, 100000), (39000.0, 1)] + [
        (39999 + position / 1000, 1) for position in range(1, 100)
    ]
    curve = calibrate_overall_rating(
        histogram, max_raw_rating=40000, lower_anchors=lower
    )
    assert curve.anchors[: len(lower)] == lower
    for raw in (50, 32000, 36001, 38999):
        assert convert_skill_rating(raw, curve.anchors) == convert_skill_rating(
            raw, lower
        )
    for position, (raw, _) in enumerate(histogram[1:]):
        assert convert_skill_rating(raw, curve.anchors) == pytest.approx(
            10
            + 0.99 * (1 - (1 - position / 99) ** (1 / 3))
            + 0.8 * position / 99 * (1 - position / 99),
            abs=0.000001,
        )
    assert convert_skill_rating(40000, curve.anchors) == 10.99
    assert curve.population == 100100
    assert curve.positive == 100


def test_tied_raw_values_share_a_tail_anchor():
    curve = calibrate_overall_rating(
        [(0.0, 10000), (39000.0, 1), (39999.9, 2)],
        max_raw_rating=40000,
        lower_anchors=[[0, 0], [39000, 10]],
    )
    assert curve.anchors[-1][0] == 39999.9
    assert curve.anchors[-1][1] == pytest.approx(10 + 0.99 * (1 - 0.5 ** (1 / 3)) + 0.2)
    assert curve.ties == 10000


def test_sparse_population_does_not_gain_level_ten():
    curve = calibrate_overall_rating([(0, 5), (100, 2), (200, 1)], max_raw_rating=40000)
    assert curve.anchors[-1][1] < 10


@pytest.mark.parametrize("size", [119, 1190])
def test_mid_tail_threshold_scales_with_population(size):
    histogram = [(0.0, size * 1000)] + [(39000 + i / 10, 1) for i in range(size)]
    curve = calibrate_overall_rating(
        histogram, max_raw_rating=40000, lower_anchors=[[0, 0], [39000, 10]]
    )
    count = sum(
        convert_skill_rating(raw, curve.anchors) >= 10.5 for raw, _ in histogram[1:]
    )
    assert count / size == pytest.approx(35 / 119, abs=0.01)
    if size == 119:
        assert count == 35


@pytest.mark.parametrize("exponent", [0.01, 0.1, 1 / 3, 0.5, 1])
def test_mid_tail_lift_remains_monotone(exponent):
    curve = calibrate_overall_rating(
        [(0, 100000)] + [(39000 + i / 100, 1) for i in range(1000)],
        max_raw_rating=40000,
        lower_anchors=[[0, 0], [39000, 10]],
        tail_exponent=exponent,
    )
    outputs = [display for _, display in curve.anchors]
    assert outputs == sorted(outputs)
    assert outputs[-1] == 10.99


def test_other_scopes_can_distinguish_results_inside_the_final_ovr_interval():
    histogram = [(0.0, 100000)] + [(39000.0 + i * 8, 1) for i in range(117)]
    histogram += [(39995.061161, 1), (39999.999999, 1)]
    curve = calibrate_overall_rating(
        histogram, max_raw_rating=40000, lower_anchors=[[0, 0], [39000, 10]]
    )
    values = [39992.312324, 39998.208229, 39999.484536, 39999.807643]
    displays = [convert_skill_rating(raw, curve.anchors) for raw in values]
    assert len({floor(value * 100) for value in displays}) == 4
    assert displays == sorted(displays)
    assert all(10 <= value <= 10.99 for value in displays)


@pytest.mark.parametrize("raw", [float("nan"), float("inf"), -1, 40001])
def test_invalid_histograms_are_rejected(raw):
    with pytest.raises(ValueError):
        calibrate_overall_rating([(raw, 1)], max_raw_rating=40000)
