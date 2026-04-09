from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
import tomllib

_RANK_SYSTEM_CONFIG_PATH = Path(__file__).resolve().parents[2] / "rank-system.toml"


@dataclass(frozen=True, slots=True)
class RatingSettings:
    decay: Decimal
    max_map_points: int
    target_max_raw_rating: int

    @property
    def multiplier(self) -> Decimal:
        return (
            Decimal(self.target_max_raw_rating) * (Decimal("1") - self.decay)
        ) / Decimal(self.max_map_points)


@dataclass(frozen=True, slots=True)
class PointsSettings:
    shared_min_points_by_tier: dict[int, int]
    rank_weight: float
    top_100_increment: float
    top_20_increment: float
    top_five_bonuses: dict[int, float]
    dist_fallback_threshold: int
    dist_fallback_base: float
    dist_fallback_tier_scale: float
    dist_fallback_center: float

    @property
    def dist_weight(self) -> float:
        return 1.0 - self.rank_weight


@dataclass(frozen=True, slots=True)
class RankSystemSettings:
    rating: RatingSettings
    points: PointsSettings


def _parse_int_keyed_int_dict(value: object, *, field_name: str) -> dict[int, int]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a table")
    return {int(key): int(raw_value) for key, raw_value in value.items()}


def _parse_int_keyed_float_dict(
    value: object,
    *,
    field_name: str,
) -> dict[int, float]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a table")
    return {int(key): float(raw_value) for key, raw_value in value.items()}


def load_rank_system_settings(
    *,
    path: Path | None = None,
) -> RankSystemSettings:
    config_path = path or _RANK_SYSTEM_CONFIG_PATH
    with config_path.open("rb") as config_file:
        raw_settings = tomllib.load(config_file)

    raw_rating = raw_settings["rating"]
    raw_points = raw_settings["points"]

    return RankSystemSettings(
        rating=RatingSettings(
            decay=Decimal(str(raw_rating["decay"])),
            max_map_points=int(raw_rating["max_map_points"]),
            target_max_raw_rating=int(raw_rating["target_max_raw_rating"]),
        ),
        points=PointsSettings(
            shared_min_points_by_tier=_parse_int_keyed_int_dict(
                raw_points["shared_min_points_by_tier"],
                field_name="points.shared_min_points_by_tier",
            ),
            rank_weight=float(raw_points["rank_weight"]),
            top_100_increment=float(raw_points["top_100_increment"]),
            top_20_increment=float(raw_points["top_20_increment"]),
            top_five_bonuses=_parse_int_keyed_float_dict(
                raw_points["top_five_bonuses"],
                field_name="points.top_five_bonuses",
            ),
            dist_fallback_threshold=int(raw_points["dist_fallback_threshold"]),
            dist_fallback_base=float(raw_points["dist_fallback_base"]),
            dist_fallback_tier_scale=float(raw_points["dist_fallback_tier_scale"]),
            dist_fallback_center=float(raw_points["dist_fallback_center"]),
        ),
    )


@lru_cache(maxsize=1)
def get_rank_system_settings() -> RankSystemSettings:
    return load_rank_system_settings()


def clear_rank_system_settings_cache() -> None:
    get_rank_system_settings.cache_clear()
