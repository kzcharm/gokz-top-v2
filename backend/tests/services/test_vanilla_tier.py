import pytest

from app.services.vanilla_tier import (
    VanillaTierEntry,
    normalize_vanilla_tier_map_name,
    parse_map_tiers_csv,
    parse_uncompleted_maps_csv,
)


def test_parse_map_tiers_csv_reads_numeric_tp_and_pro_tiers() -> None:
    csv_text = '\n'.join(
        [
            '"Map Name","TP Tier","PRO Tier"',
            '"kz_alpha","3","5"',
            '"kz_beta ","4",""',
            '"kz_gamma","N/A","7"',
            '"ignored","",""',
        ]
    )

    parsed = parse_map_tiers_csv(csv_text)

    assert parsed == {
        "kz_alpha": VanillaTierEntry(tp_tier=3, pro_tier=5),
        "kz_beta": VanillaTierEntry(tp_tier=4, pro_tier=None),
        "kz_gamma": VanillaTierEntry(tp_tier=None, pro_tier=7),
    }


def test_parse_uncompleted_maps_csv_collects_only_normalized_map_names() -> None:
    csv_text = '\n'.join(
        [
            '"Feasible Maps Unfeasible Maps","Global Tier Global Tier"',
            '"kz_alpha ","5"',
            '"Impossible Maps","","Notes"',
            '"bkz_beta","4"',
            '"Definition","",""',
            '"random text","",""',
        ]
    )

    parsed = parse_uncompleted_maps_csv(csv_text)

    assert parsed == {"kz_alpha", "bkz_beta"}


def test_normalize_vanilla_tier_map_name_trims_and_lowercases() -> None:
    assert normalize_vanilla_tier_map_name(" KZ_Submerged ") == "kz_submerged"
