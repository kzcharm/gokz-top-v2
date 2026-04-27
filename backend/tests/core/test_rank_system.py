from decimal import Decimal
from pathlib import Path

from app.core.rank_system import load_rank_system_settings


def test_load_rank_system_settings_parses_current_config() -> None:
    settings = load_rank_system_settings()

    assert settings.rating.decay == Decimal("0.975")
    assert settings.rating.max_map_points == 1000
    assert settings.rating.target_max_raw_rating == 40000
    assert settings.rating.multiplier == Decimal("1.000")
    assert settings.points.shared_min_points_by_tier[4] == 350
    assert settings.points.top_five_bonuses[1] == 0.20
    assert settings.points.dist_weight == 0.875


def test_load_rank_system_settings_computes_legacy_multiplier(tmp_path: Path) -> None:
    config_path = tmp_path / "rank-system.toml"
    config_path.write_text(
        "\n".join(
            [
                "[rating]",
                "decay = 0.975",
                "max_map_points = 1000",
                "target_max_raw_rating = 40000",
                "",
                "[points]",
                'shared_min_points_by_tier = { "1" = 1, "2" = 50, "3" = 200, "4" = 400, "5" = 600, "6" = 800, "7" = 900, "8" = 970 }',
                "rank_weight = 0.125",
                "top_100_increment = 0.004",
                "top_20_increment = 0.02",
                'top_five_bonuses = { "1" = 0.20, "2" = 0.12, "3" = 0.09, "4" = 0.06, "5" = 0.02 }',
                "dist_fallback_threshold = 50",
                "dist_fallback_base = 2.1",
                "dist_fallback_tier_scale = 0.25",
                "dist_fallback_center = 1.5",
            ]
        ),
        encoding="utf-8",
    )

    settings = load_rank_system_settings(path=config_path)

    assert settings.rating.multiplier == Decimal("1")
    assert settings.points.dist_weight == 0.875
