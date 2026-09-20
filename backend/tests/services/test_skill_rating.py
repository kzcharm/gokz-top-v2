from decimal import Decimal
from math import floor

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
        [(raw, 1) for raw in range(1024)],
        max_raw_rating=40_000,
    )

    assert [anchor for anchor in result.anchors if anchor[1] >= 2] == [
        [512, 2],
        [768, 3],
        [896, 4],
        [960, 5],
        [992, 6],
        [1008, 7],
        [1016, 8],
        [1020, 9],
        [1022, 10],
        [1023, TOP_DISPLAY_RATING],
    ]
    assert convert_skill_rating(1022, result.anchors) == 10
    assert convert_skill_rating(1023, result.anchors) == TOP_DISPLAY_RATING
    assert convert_skill_rating(40_000, result.anchors) == TOP_DISPLAY_RATING
    assert floor((convert_skill_rating(1023, result.anchors) or 0) * 100) / 100 == 10.99


def test_unique_leader_stays_below_eleven_and_floors_to_10_99() -> None:
    result = calibrate(
        [(raw, 1) for raw in range(1024)] + [(40_000, 1)],
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
    histogram = [(raw, 1) for raw in range(1023)] + [(1023, 2)]
    result = calibrate(histogram, max_raw_rating=40_000)

    assert result.anchors[-1] == [1023, TIED_TOP_DISPLAY_RATING]
    assert convert_skill_rating(1023, result.anchors) == TIED_TOP_DISPLAY_RATING
    assert floor((convert_skill_rating(1023, result.anchors) or 0) * 100) / 100 == 10.99


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
