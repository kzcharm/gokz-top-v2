from itertools import pairwise

import pytest

from app.models.leaderboard_player import (
    min_raw_rating_for_public_rating,
    redistribute_display_rating,
    scale_public_rating,
)


@pytest.mark.parametrize(
    ("old_rating", "new_rating"),
    [
        (1.14825, 1.0),
        (2.972, 2.0),
        (5.3625, 3.0),
        (7.5185, 4.0),
        (8.763, 5.0),
        (9.3665, 6.0),
        (9.6935, 7.0),
        (9.9585, 8.0),
        (10.22725, 9.0),
        (10.49825, 10.0),
        (11.0, 11.0),
    ],
)
def test_redistribute_display_rating_returns_anchor_points_exactly(
    old_rating: float,
    new_rating: float,
) -> None:
    assert redistribute_display_rating(old_rating) == pytest.approx(new_rating)


def test_redistribute_display_rating_is_monotonic_and_bounded() -> None:
    inputs = [1 + (index / 100) for index in range(0, 1001)]
    outputs = [redistribute_display_rating(value) for value in inputs]

    assert all(1.0 <= value <= 11.0 for value in outputs)
    assert all(left <= right for left, right in pairwise(outputs))


@pytest.mark.parametrize(
    ("input_rating", "expected_rating"),
    [
        (0.0, 1.0),
        (1.0, 1.0),
        (1.1, 1.0),
        (11.0, 11.0),
        (11.5, 11.0),
        (12.0, 11.0),
    ],
)
def test_redistribute_display_rating_clamps_input(
    input_rating: float,
    expected_rating: float,
) -> None:
    assert redistribute_display_rating(input_rating) == pytest.approx(expected_rating)


def test_scale_public_rating_returns_none_for_unrated_values() -> None:
    assert scale_public_rating(None) is None
    assert scale_public_rating(0) is None


def test_scale_public_rating_composes_linear_scale_and_redistribution() -> None:
    assert scale_public_rating(40_000) == pytest.approx(11.0)
    assert scale_public_rating(37_993) == pytest.approx(10.0)
    assert scale_public_rating(36_775) < 10.0
    assert scale_public_rating(4_000) == pytest.approx(redistribute_display_rating(2.0))


@pytest.mark.parametrize("target_rating", [1, 6, 7, 8, 9, 10, 11])
def test_min_raw_rating_for_public_rating_returns_smallest_matching_raw_rating(
    target_rating: int,
) -> None:
    threshold = min_raw_rating_for_public_rating(target_rating)

    assert scale_public_rating(threshold) >= target_rating
    if threshold > 1:
        assert scale_public_rating(threshold - 1) < target_rating


def test_min_raw_rating_for_public_rating_is_monotonic() -> None:
    thresholds = [
        min_raw_rating_for_public_rating(target_rating)
        for target_rating in range(1, 12)
    ]

    assert all(left <= right for left, right in pairwise(thresholds))


def test_difficulty_display_ratings_are_not_scaled_twice() -> None:
    from app.models import ModeScope, PlayerLeaderboardRankPublic, PlayerRefPublic

    row = PlayerLeaderboardRankPublic(
        scope=ModeScope.OVR,
        player=PlayerRefPublic(steamid64="76561198000000000", display_name="Test"),
        rating=40000,
        rating_easy=7.25,
        rating_hard=None,
        points=0,
        wrs_nub=0,
        wrs_pro=0,
        records_900_plus=0,
        records_800_plus=0,
        unique_map_finishes=10,
    )
    payload = row.model_dump(mode="json")
    assert payload["rating"] == 11
    assert payload["rating_easy"] == 7.25
    assert payload["rating_hard"] is None
