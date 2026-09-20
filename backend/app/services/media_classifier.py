from __future__ import annotations

import re
from collections.abc import Iterable
from enum import StrEnum
from typing import NamedTuple


class MediaMatchReason(StrEnum):
    TAG = "tag"
    TITLE_KEYWORD = "title_keyword"
    DESCRIPTION_KEYWORD = "description_keyword"
    TITLE_MAP = "title_map"
    DESCRIPTION_MAP = "description_map"
    NO_MATCH = "no_match"


class MediaClassification(NamedTuple):
    is_kz_video: bool
    reason: MediaMatchReason


_KZ_TAGS = frozenset({"kz", "gokz", "kreedz", "cs2kz"})
_KEYWORD_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])(?:KZ|GOKZ|Kreedz|CS2KZ)(?![A-Za-z0-9])",
    re.IGNORECASE | re.ASCII,
)
_MAP_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])(?:kz|bkz|kzpro|xc)_[A-Za-z0-9]+"
    r"(?:[A-Za-z0-9_-]*[A-Za-z0-9])?(?![A-Za-z0-9_])",
    re.IGNORECASE | re.ASCII,
)


def classify_media_post(
    *, title: str | None, description: str | None, tags: Iterable[str] | None
) -> MediaClassification:
    """Classify platform-neutral video metadata using deterministic precedence."""
    if tags is not None and any(tag.strip().casefold() in _KZ_TAGS for tag in tags):
        return MediaClassification(True, MediaMatchReason.TAG)
    if title and _KEYWORD_PATTERN.search(title):
        return MediaClassification(True, MediaMatchReason.TITLE_KEYWORD)
    if description and _KEYWORD_PATTERN.search(description):
        return MediaClassification(True, MediaMatchReason.DESCRIPTION_KEYWORD)
    if title and _MAP_PATTERN.search(title):
        return MediaClassification(True, MediaMatchReason.TITLE_MAP)
    if description and _MAP_PATTERN.search(description):
        return MediaClassification(True, MediaMatchReason.DESCRIPTION_MAP)
    return MediaClassification(False, MediaMatchReason.NO_MATCH)


__all__ = ["MediaClassification", "MediaMatchReason", "classify_media_post"]
