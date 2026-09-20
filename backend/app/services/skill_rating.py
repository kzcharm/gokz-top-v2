"""Virtual-entry ratings for the six analyzed map skills."""

from collections.abc import Iterable
from decimal import Decimal
from math import exp, expm1, log

from app.core.rank_system import get_rank_system_settings

SKILLS = ("boxtech", "strafe", "bhop", "climb", "ladder", "slide")


def calculate_skill_rating(
    points_and_portions: Iterable[tuple[int, Decimal] | tuple[int, Decimal, int]],
    *,
    full_portion_decay: float | None = None,
    max_full_portion_entries: float | None = None,
) -> int:
    """Rate virtual PB-point entries without materializing their repeated list.

    A portion of 1 represents 100 entries, and a portion of 0.005 is half
    an entry. The full-portion decay determines their collective retention.
    Each skill independently keeps the highest-point evidence up to the amount
    expected from the configured number of evenly distributed six-skill maps.
    """
    settings = get_rank_system_settings().rating
    decay = (
        float(settings.skill_full_portion_decay)
        if full_portion_decay is None
        else full_portion_decay
    )
    if not 0 < decay < 1:
        raise ValueError("skill_full_portion_decay must be between zero and one")
    entry_limit = float(
        settings.skill_top_map_equivalents / len(SKILLS)
        if max_full_portion_entries is None
        else max_full_portion_entries
    )
    if entry_limit <= 0:
        raise ValueError("skill entry limit must be positive")
    log_decay = log(decay)
    total = 0.0
    consumed = 0.0
    entries = sorted(
        points_and_portions,
        key=lambda row: (-row[0], row[2] if len(row) == 3 else 0),
    )
    for entry in entries:
        points, portion = entry[:2]
        fraction = min(float(portion), entry_limit - consumed)
        if fraction <= 0:
            continue
        total += points * exp(consumed * log_decay) * -expm1(fraction * log_decay)
        consumed += fraction
        if consumed >= entry_limit:
            break
    return min(
        settings.target_max_raw_rating,
        int(total * settings.target_max_raw_rating / settings.max_map_points),
    )
