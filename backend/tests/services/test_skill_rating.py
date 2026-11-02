from decimal import Decimal
from math import floor

import pytest

from app.services.skill_rating import calculate_skill_rating
from app.services.skill_rating_converter import (
    RUNNER_UP_DISPLAY_CEILING,
    TIED_TOP_DISPLAY_RATING,
    TOP_DISPLAY_RATING,
    calibrate,
    convert_skill_rating,
)


def test_fractional_virtual_entries_preserve_intact_points() -> None:
    assert calculate_skill_rating([(900, Decimal("0.5"))]) == 1847
    assert calculate_skill_rating([(700, Decimal("1"))]) == 2799
    assert calculate_skill_rating([(900, Decimal("0.01"))]) < calculate_skill_rating(
        [(700, Decimal("1"))]
    )
    assert calculate_skill_rating([(900, Decimal("0"))]) == 0
    assert calculate_skill_rating([(900, Decimal("1"))]) == 3599
    assert calculate_skill_rating([(900, Decimal("0.005"))]) > 0
    assert calculate_skill_rating([(900, Decimal("0.0001"))]) < calculate_skill_rating(
        [(900, Decimal("0.005"))]
    )


def test_skill_rating_is_order_independent_and_capped() -> None:
    rows = [(900, Decimal("0.5")), (700, Decimal("1"))]
    assert calculate_skill_rating(rows) == calculate_skill_rating(reversed(rows))
    tied_rows = [
        (900, Decimal("0.001"), 2),
        (900, Decimal("0.999"), 1),
    ]
    assert calculate_skill_rating(tied_rows) == calculate_skill_rating(
        reversed(tied_rows)
    )
    assert (
        calculate_skill_rating(
            [(1000, Decimal("1"))] * 1000,
            max_full_portion_entries=1000,
        )
        == 40000
    )
    assert calculate_skill_rating([(2000, Decimal("1"))] * 1000) == 40000


def test_skill_rating_caps_highest_point_virtual_evidence_per_skill() -> None:
    rows = [
        (900, Decimal("0"), 1),
        (800, Decimal("1"), 2),
        (700, Decimal("1"), 3),
    ]

    assert calculate_skill_rating(
        rows, max_full_portion_entries=Decimal("1.5")
    ) == calculate_skill_rating(
        [(800, Decimal("1"), 2), (700, Decimal("0.5"), 3)],
        max_full_portion_entries=Decimal("1.5"),
    )
    assert calculate_skill_rating(
        rows, max_full_portion_entries=2
    ) > calculate_skill_rating(rows, max_full_portion_entries=Decimal("1.5"))


def test_skill_rating_default_cap_equals_one_sixth_of_50_maps() -> None:
    one_sixth = Decimal(1) / 6
    first_50 = [(1000 - index, one_sixth, index) for index in range(50)]
    lower_51st = (1, one_sixth, 50)

    assert calculate_skill_rating([*first_50, lower_51st]) == calculate_skill_rating(
        first_50
    )


def test_skill_rating_entry_limit_validates_and_breaks_point_ties_by_map() -> None:
    rows = [
        (900, Decimal("1"), 2),
        (900, Decimal("0.5"), 1),
    ]

    assert calculate_skill_rating(
        rows, max_full_portion_entries=Decimal("0.5")
    ) == calculate_skill_rating(
        [(900, Decimal("0.5"), 1)],
        max_full_portion_entries=Decimal("0.5"),
    )
    try:
        calculate_skill_rating(rows, max_full_portion_entries=0)
    except ValueError as error:
        assert str(error) == "skill entry limit must be positive"
    else:
        raise AssertionError("expected an invalid map limit to fail")


def test_lower_full_portion_decay_concentrates_rating_in_earlier_runs() -> None:
    rows = [(900, Decimal("0.5")), (700, Decimal("1"))]
    assert calculate_skill_rating(
        rows, full_portion_decay=0.9
    ) > calculate_skill_rating(rows, full_portion_decay=0.99)


def test_entry_cap_rewards_high_points_over_completion_breadth() -> None:
    completion_heavy = [
        (910, Decimal("1.21")),
        (820, Decimal("28.38")),
        (750, Decimal("7.11")),
        (600, Decimal("1.13")),
    ]
    high_point_heavy = [
        (950, Decimal("13.99")),
        (850, Decimal("5.13")),
        (750, Decimal("3.41")),
        (600, Decimal("2.35")),
    ]

    assert calculate_skill_rating(
        high_point_heavy, full_portion_decay=0.975
    ) > calculate_skill_rating(completion_heavy, full_portion_decay=0.975)
    assert calculate_skill_rating(high_point_heavy) > calculate_skill_rating(
        completion_heavy
    )


def test_converter_uses_strictly_lower_players_and_retains_ties() -> None:
    result = calibrate([(0, 5), (100, 2), (200, 1)], max_raw_rating=40_000)
    assert result.population == 8
    assert result.positive == 3
    assert result.ties == 5
    assert result.anchors == [[0, 0], [100, 2], [200, 4]]
    assert convert_skill_rating(50, result.anchors) == 1
    assert convert_skill_rating(100, result.anchors) == 2
    assert convert_skill_rating(150, result.anchors) == 3
    assert convert_skill_rating(0, result.anchors) is None
    assert convert_skill_rating(500, result.anchors) == 4


def test_converter_avoids_splitting_upper_tail_ties() -> None:
    result = calibrate([(0, 2), (100, 8)], max_raw_rating=40_000)
    assert result.anchors == [[0, 0], [100, 1]]
    assert convert_skill_rating(100, result.anchors) == 1


def test_converter_maps_population_best_just_below_level_eleven() -> None:
    result = calibrate(
        [(raw, 1) for raw in range(2048)],
        max_raw_rating=40_000,
    )

    assert [anchor for anchor in result.anchors if anchor[1] >= 2] == [
        [1024, 2],
        [1536, 3],
        [1792, 4],
        [1920, 5],
        [1984, 6],
        [2016, 7],
        [2032, 8],
        [2042, 9],
        [2046, 10],
        [2047, TOP_DISPLAY_RATING],
    ]
    assert convert_skill_rating(2046, result.anchors) == 10
    assert convert_skill_rating(2047, result.anchors) == TOP_DISPLAY_RATING
    assert convert_skill_rating(40_000, result.anchors) == TOP_DISPLAY_RATING
    assert floor((convert_skill_rating(2047, result.anchors) or 0) * 100) / 100 == 10.99


def test_unique_leader_stays_below_eleven_and_floors_to_10_99() -> None:
    result = calibrate(
        [(raw, 1) for raw in range(2048)] + [(40_000, 1)],
        max_raw_rating=40_000,
    )

    assert result.anchors[-2:] == [
        [39_999, RUNNER_UP_DISPLAY_CEILING],
        [40_000, TOP_DISPLAY_RATING],
    ]
    assert (
        floor((convert_skill_rating(39_999, result.anchors) or 0) * 100) / 100 == 10.99
    )
    assert (
        floor((convert_skill_rating(40_000, result.anchors) or 0) * 100) / 100 == 10.99
    )
    assert (convert_skill_rating(40_000, result.anchors) or 0) < 11


def test_converter_keeps_tied_population_best_equal() -> None:
    histogram = [(raw, 1) for raw in range(2047)] + [(2047, 2)]
    result = calibrate(histogram, max_raw_rating=40_000)

    assert result.anchors[-1] == [2047, TIED_TOP_DISPLAY_RATING]
    assert convert_skill_rating(2047, result.anchors) == TIED_TOP_DISPLAY_RATING
    assert floor((convert_skill_rating(2047, result.anchors) or 0) * 100) / 100 == 10.99


def test_curve_preserves_lower_levels_and_steepens_upper_tail() -> None:
    histogram = [(raw, 1) for raw in range(4096)]
    previous = calibrate(histogram, max_raw_rating=40000, tail_multiplier=1)
    current = calibrate(histogram, max_raw_rating=40000)
    for level in range(2, 11):
        old_count = sum(
            n
            for raw, n in histogram
            if (convert_skill_rating(raw, previous.anchors) or 0) >= level
        )
        new_count = sum(
            n
            for raw, n in histogram
            if (convert_skill_rating(raw, current.anchors) or 0) >= level
        )
        if level <= 8:
            assert new_count == old_count == 4096 // 2 ** (level - 1)
        elif level == 9:
            assert new_count == 12  # Between 32 at 8+ and 4 at 10+, geometrically.
        else:
            assert new_count == old_count // 2 == 4

    # The entire displayed curve below level eight is unchanged, not only
    # the integer thresholds. No player identity enters this calculation.
    for raw in range(4065):
        assert convert_skill_rating(raw, current.anchors) == convert_skill_rating(
            raw, previous.anchors
        )


def test_stricter_curve_keeps_boundary_ties_together() -> None:
    histogram = [(raw, 1) for raw in range(104000)] + [(104000, 379)]
    result = calibrate(histogram, max_raw_rating=200000)
    # A tied group larger than the entire qualifying tail cannot be split.
    assert (convert_skill_rating(104000, result.anchors) or 0) < 10


def test_fractional_tail_multiplier_eases_level_ten_without_changing_level_eight() -> (
    None
):
    histogram = [(raw, 1) for raw in range(8704)]
    previous = calibrate(histogram, max_raw_rating=40000, tail_multiplier=2)
    current = calibrate(histogram, max_raw_rating=40000)

    def count(anchors: list[list[int | float]], level: int) -> int:
        return sum(
            (convert_skill_rating(raw, anchors) or 0) >= level for raw, _ in histogram
        )

    assert count(previous.anchors, 10) == 8
    assert count(current.anchors, 10) == 10
    assert count(previous.anchors, 8) == count(current.anchors, 8) == 68


@pytest.mark.parametrize("multiplier", [0, -1, float("nan"), float("inf")])
def test_converter_rejects_invalid_tail_multiplier(multiplier: float) -> None:
    with pytest.raises(ValueError, match="tail_multiplier"):
        calibrate([(100, 10)], max_raw_rating=40000, tail_multiplier=multiplier)


def test_converter_does_not_add_maximum_to_sparse_upper_tail() -> None:
    result = calibrate([(0, 2), (100, 8)], max_raw_rating=40_000)

    assert result.anchors == [[0, 0], [100, 1]]
    assert convert_skill_rating(40_000, result.anchors) == 1


def test_converter_refuses_population_without_positive_results() -> None:
    try:
        calibrate([(0, 20)], max_raw_rating=40_000)
    except ValueError:
        pass
    else:
        raise AssertionError("No-positive calibration must be rejected")
