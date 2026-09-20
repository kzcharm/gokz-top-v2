from decimal import Decimal

import numpy as np

from app.services.skill_rating import SKILLS, calculate_skill_rating
from app.services.skill_rating_converter import convert_skill_rating
from scripts.tune_skill_ratings import DTYPE, _convert_many, evaluate_raw


def test_snapshot_evaluation_matches_runtime_formula() -> None:
    runs = np.asarray(
        [
            (0, 900, 2),
            (0, 900, 3),
            (0, 700, 1),
            (2, 997, 4),
        ],
        dtype=DTYPE,
    )
    portions = np.zeros((5, len(SKILLS)), dtype=np.uint16)
    portions[1] = (10_000, 0, 1, 50, 5_000, 10_000)
    portions[2] = (5_000, 10_000, 50, 1, 2_500, 0)
    portions[3] = (2_500, 5_000, 10_000, 0, 1, 50)
    portions[4] = (10_000, 10_000, 10_000, 10_000, 10_000, 10_000)

    result = evaluate_raw(
        runs,
        portions,
        population=3,
        decay=0.9,
        max_full_portion_entries=100 / len(SKILLS),
    )

    for skill_index in range(len(SKILLS)):
        runtime_rows = [
            (
                int(run["points"]),
                Decimal(int(portions[run["map"], skill_index])) / 10_000,
            )
            for run in runs[:3]
        ]
        assert result[0, skill_index] == calculate_skill_rating(runtime_rows)
        assert result[1, skill_index] == 0
        assert result[2, skill_index] == calculate_skill_rating([(997, Decimal("1"))])


def test_snapshot_evaluation_caps_each_skills_top_point_virtual_evidence() -> None:
    runs = np.asarray(
        [(0, 900, 0), (0, 800, 1), (0, 700, 2)],
        dtype=DTYPE,
    )
    portions = np.zeros((3, len(SKILLS)), dtype=np.uint16)
    portions[1:] = 10_000

    result = evaluate_raw(
        runs,
        portions,
        population=1,
        decay=0.9,
        max_full_portion_entries=Decimal("1.5"),
    )

    for skill_index in range(len(SKILLS)):
        assert result[0, skill_index] == calculate_skill_rating(
            [(900, Decimal("0"), 0), (800, Decimal("1"), 1), (700, Decimal("1"), 2)],
            max_full_portion_entries=Decimal("1.5"),
        )


def test_vectorized_converter_matches_runtime_converter() -> None:
    anchors = [[0, 0], [100, 2], [200, 3], [500, 6], [40_000, 11]]
    values = np.asarray([0, 1, 99, 100, 150, 200, 350, 500, 20_000, 40_000])

    actual = _convert_many(values, anchors)
    expected = [convert_skill_rating(int(value), anchors) for value in values]

    for converted, expected_value in zip(actual, expected, strict=True):
        if expected_value is None:
            assert np.isnan(converted)
        else:
            assert converted == expected_value
