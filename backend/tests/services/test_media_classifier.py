import pytest

from app.services.media_classifier import MediaMatchReason, classify_media_post


@pytest.mark.parametrize("value", ["KZ", "gOkZ", "KREEDZ", "cs2kz"])
def test_classifier_accepts_exact_normalized_tags(value: str) -> None:
    result = classify_media_post(title="unrelated", description=None, tags=[value])

    assert result.is_kz_video is True
    assert result.reason == MediaMatchReason.TAG


@pytest.mark.parametrize("value", ["notkzvideo", "gokzrun", "cs2kzplus", "kreedzing"])
def test_classifier_rejects_embedded_keywords(value: str) -> None:
    assert classify_media_post(title=value, description=None, tags=[]).reason == (
        MediaMatchReason.NO_MATCH
    )


@pytest.mark.parametrize("value", ["KZ", "[GOKZ]", "CS2KZ run", "A Kreedz run"])
def test_classifier_accepts_standalone_title_keywords(value: str) -> None:
    assert classify_media_post(title=value, description=None, tags=[]).reason == (
        MediaMatchReason.TITLE_KEYWORD
    )


def test_classifier_accepts_description_keyword() -> None:
    assert (
        classify_media_post(title="A run", description="Made for GOKZ!", tags=[]).reason
        == MediaMatchReason.DESCRIPTION_KEYWORD
    )


@pytest.mark.parametrize(
    "value", ["(BKZ_GOLDHOP)", "kzpro_example-v2", "XC_DREAM"]
)
def test_classifier_accepts_complete_map_tokens(value: str) -> None:
    assert classify_media_post(title=value, description=None, tags=[]).reason == (
        MediaMatchReason.TITLE_MAP
    )


@pytest.mark.parametrize(
    "value",
    ["bkz_", "prefixbkz_map", "prefix_bkz_map", "bkz__map", "bkz_map_suffix_"],
)
def test_classifier_rejects_malformed_or_embedded_map_tokens(value: str) -> None:
    assert classify_media_post(title=value, description=None, tags=[]).reason == (
        MediaMatchReason.NO_MATCH
    )


def test_classifier_uses_deterministic_precedence() -> None:
    assert (
        classify_media_post(
            title="KZ on kz_map", description="Kreedz", tags=["CS2KZ"]
        ).reason
        == MediaMatchReason.TAG
    )
    assert (
        classify_media_post(title="GOKZ kz_map", description="Kreedz", tags=[]).reason
        == MediaMatchReason.TITLE_KEYWORD
    )
    assert (
        classify_media_post(title="kz_map", description="Kreedz", tags=[]).reason
        == MediaMatchReason.TITLE_KEYWORD
    )
    assert (
        classify_media_post(title="bkz_map", description="Kreedz", tags=[]).reason
        == MediaMatchReason.DESCRIPTION_KEYWORD
    )
