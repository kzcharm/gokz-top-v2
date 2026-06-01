import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.models import PlayerSocialPlatform

SOCIAL_PLATFORM_ORDER = (
    PlayerSocialPlatform.BILIBILI,
    PlayerSocialPlatform.GITHUB,
    PlayerSocialPlatform.TWITCH,
    PlayerSocialPlatform.X,
    PlayerSocialPlatform.YOUTUBE,
)

_USERNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
_X_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{1,15}$")
_BILIBILI_UID_RE = re.compile(r"^[1-9][0-9]{0,19}$")
_YOUTUBE_CHANNEL_RE = re.compile(r"^UC[A-Za-z0-9_-]{20,}$")
_YOUTUBE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


@dataclass(frozen=True, slots=True)
class ParsedPlayerSocialLink:
    platform: PlayerSocialPlatform
    account_identifier: str


def parse_player_social_link_url(url: str) -> ParsedPlayerSocialLink | None:
    normalized_url = _normalize_url_for_parse(url)
    if normalized_url is None:
        return None

    parsed = urlsplit(normalized_url)
    host = parsed.netloc.split(":", maxsplit=1)[0].lower()
    if host.startswith("www."):
        host = host[4:]

    path_segments = [segment for segment in parsed.path.split("/") if segment]
    if not path_segments:
        return None

    if host in {"x.com", "twitter.com"}:
        return _parse_username_platform(
            platform=PlayerSocialPlatform.X,
            path_segments=path_segments,
            pattern=_X_USERNAME_RE,
            lower=True,
        )

    if host == "space.bilibili.com":
        uid = path_segments[0]
        if _BILIBILI_UID_RE.fullmatch(uid):
            return ParsedPlayerSocialLink(
                platform=PlayerSocialPlatform.BILIBILI,
                account_identifier=uid,
            )
        return None

    if host in {"github.com", "gist.github.com"}:
        return _parse_username_platform(
            platform=PlayerSocialPlatform.GITHUB,
            path_segments=path_segments,
            pattern=_USERNAME_RE,
            lower=True,
        )

    if host == "twitch.tv":
        return _parse_username_platform(
            platform=PlayerSocialPlatform.TWITCH,
            path_segments=path_segments,
            pattern=_USERNAME_RE,
            lower=True,
        )

    if host in {"youtube.com", "m.youtube.com"}:
        return _parse_youtube_path(path_segments)

    return None


def build_player_social_link_url(
    *, platform: PlayerSocialPlatform, account_identifier: str
) -> str:
    if platform == PlayerSocialPlatform.BILIBILI:
        return f"https://space.bilibili.com/{account_identifier}"
    if platform == PlayerSocialPlatform.GITHUB:
        return f"https://github.com/{account_identifier}"
    if platform == PlayerSocialPlatform.TWITCH:
        return f"https://www.twitch.tv/{account_identifier}"
    if platform == PlayerSocialPlatform.X:
        return f"https://x.com/{account_identifier}"
    if platform == PlayerSocialPlatform.YOUTUBE:
        return f"https://www.youtube.com/{account_identifier}"
    raise ValueError(f"Unsupported social platform: {platform}")


def _normalize_url_for_parse(url: str) -> str | None:
    normalized = url.strip()
    if not normalized:
        return None
    if not normalized.startswith(("http://", "https://")):
        normalized = f"https://{normalized}"

    parsed = urlsplit(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return normalized


def _parse_username_platform(
    *,
    platform: PlayerSocialPlatform,
    path_segments: list[str],
    pattern: re.Pattern[str],
    lower: bool,
) -> ParsedPlayerSocialLink | None:
    if len(path_segments) != 1:
        return None
    username = path_segments[0].strip()
    if username.lower() in {
        "about",
        "business",
        "directory",
        "explore",
        "home",
        "i",
        "login",
        "notifications",
        "p",
        "search",
        "settings",
        "share",
        "signup",
    }:
        return None
    if not pattern.fullmatch(username):
        return None
    return ParsedPlayerSocialLink(
        platform=platform,
        account_identifier=username.lower() if lower else username,
    )


def _parse_youtube_path(
    path_segments: list[str],
) -> ParsedPlayerSocialLink | None:
    first_segment = path_segments[0]
    if first_segment.startswith("@"):
        handle = first_segment[1:]
        if not _YOUTUBE_NAME_RE.fullmatch(handle):
            return None
        return ParsedPlayerSocialLink(
            platform=PlayerSocialPlatform.YOUTUBE,
            account_identifier=f"@{handle.lower()}",
        )

    if first_segment == "channel" and len(path_segments) >= 2:
        channel_id = path_segments[1]
        if not _YOUTUBE_CHANNEL_RE.fullmatch(channel_id):
            return None
        return ParsedPlayerSocialLink(
            platform=PlayerSocialPlatform.YOUTUBE,
            account_identifier=f"channel/{channel_id}",
        )

    if first_segment == "user" and len(path_segments) >= 2:
        name = path_segments[1]
        if not _YOUTUBE_NAME_RE.fullmatch(name):
            return None
        return ParsedPlayerSocialLink(
            platform=PlayerSocialPlatform.YOUTUBE,
            account_identifier=f"{first_segment}/{name}",
        )

    return None
