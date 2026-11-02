from decimal import Decimal
from pathlib import Path

import pytest

from app.core.config import settings as app_settings
from app.core.rank_system import (
    clear_rank_system_settings_cache,
    get_rank_system_settings,
    load_rank_system_settings,
)


def test_preview_curve_override_is_local_and_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    anchors = [[0, 0], [100, 1], [40000, 10.99]]
    original = load_rank_system_settings().display_anchors
    monkeypatch.setattr(app_settings, "LOCAL_OVR_RATING_DISPLAY_ANCHORS", anchors)
    monkeypatch.setattr(app_settings, "LOCAL_OVR_NUB_RANK_POINTS_PREVIEW", True)
    monkeypatch.setattr(app_settings, "ENVIRONMENT", "local")
    try:
        clear_rank_system_settings_cache()
        assert get_rank_system_settings().display_anchors == anchors
        monkeypatch.setattr(app_settings, "ENVIRONMENT", "production")
        clear_rank_system_settings_cache()
        assert get_rank_system_settings().display_anchors == original
        monkeypatch.setattr(app_settings, "ENVIRONMENT", "local")
        monkeypatch.setattr(app_settings, "LOCAL_OVR_NUB_RANK_POINTS_PREVIEW", False)
        clear_rank_system_settings_cache()
        assert get_rank_system_settings().display_anchors == original
    finally:
        clear_rank_system_settings_cache()


def test_load_rank_system_settings_parses_current_config() -> None:
    settings = load_rank_system_settings()

    assert settings.rating.easy_top_maps is None
    assert settings.rating.hard_top_maps is None
    assert settings.rating.decay == Decimal("0.95")
    assert settings.rating.skill_full_portion_decay == Decimal("0.9")
    assert settings.rating.skill_top_map_equivalents == 50
    assert settings.rating.max_map_points == 1000
    assert settings.rating.target_max_raw_rating == 40000
    assert settings.rating.multiplier == Decimal("2")
    assert settings.display_anchors is not None
    assert settings.display_anchors[-1][1] <= 10.99999
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
                "skill_full_portion_decay = 0.9",
                "skill_top_map_equivalents = 50",
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
