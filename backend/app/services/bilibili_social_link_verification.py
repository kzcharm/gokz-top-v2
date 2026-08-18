from __future__ import annotations

import html
import re
import uuid
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from typing import Any

import httpx
import jwt
from jwt.exceptions import InvalidTokenError
from pydantic import BaseModel, ValidationError

from app.core import security
from app.core.config import settings

BILIBILI_PROFILE_URL = "https://space.bilibili.com/{uid}"
BILIBILI_PENDING_CONFIRM_TTL = timedelta(minutes=10)
_BILIBILI_DESCRIPTION_PREFIX_RE = re.compile(
    r"^哔哩哔哩.*?第一时间了解UP主动态。",
    re.DOTALL,
)
_BILIBILI_BROWSER_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/136.0.0.0 Safari/537.36"
    ),
}


def _bilibili_headers() -> dict[str, str]:
    headers = dict(_BILIBILI_BROWSER_HEADERS)
    if settings.BILIBILI_COOKIE:
        headers["Cookie"] = settings.BILIBILI_COOKIE
    return headers


class BilibiliVerificationPendingPayload(BaseModel):
    purpose: str
    steamid64: int
    link_id: str
    platform: str
    current_account_identifier: str
    verification_code: str
    exp: int


class BilibiliProfileVerificationCodeMissingError(ValueError):
    pass


class BilibiliProfileFetchError(ValueError):
    pass


class _DescriptionMetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.description: str | None = None

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag.lower() != "meta" or self.description is not None:
            return

        attr_map = {key.lower(): value for key, value in attrs if value is not None}
        if attr_map.get("name", "").lower() != "description":
            return

        content = attr_map.get("content")
        if content is not None:
            self.description = html.unescape(content).strip()


def create_bilibili_pending_confirmation_token(
    *,
    steamid64: int,
    link_id: str,
    current_account_identifier: str,
    verification_code: str | None = None,
    expires_at: datetime | None = None,
) -> tuple[str, str, datetime]:
    expires_at = expires_at or (datetime.now(UTC) + BILIBILI_PENDING_CONFIRM_TTL)
    verification_code = verification_code or _build_bilibili_verification_code()
    payload = BilibiliVerificationPendingPayload(
        purpose="bilibili_social_link_verify_pending",
        steamid64=steamid64,
        link_id=link_id,
        platform="bilibili",
        current_account_identifier=current_account_identifier,
        verification_code=verification_code,
        exp=int(expires_at.timestamp()),
    )
    token = jwt.encode(
        payload.model_dump(mode="json"),
        settings.SECRET_KEY,
        algorithm=security.ALGORITHM,
    )
    return token, verification_code, expires_at


def is_uuid_profile_text(profile_text: str) -> bool:
    try:
        uuid.UUID(profile_text.strip())
    except (ValueError, AttributeError):
        return False
    return True


def get_bilibili_pending_metadata(
    *, metadata_json: dict[str, Any] | None, account_identifier: str, now: datetime
) -> tuple[str, datetime, str | None] | None:
    if not metadata_json:
        return None
    pending = metadata_json.get("bilibili_verification")
    if not isinstance(pending, dict):
        return None
    if pending.get("account_identifier") != account_identifier:
        return None
    code = pending.get("verification_code")
    expires_at_value = pending.get("expires_at")
    if not isinstance(code, str) or not isinstance(expires_at_value, str):
        return None
    try:
        expires_at = datetime.fromisoformat(expires_at_value)
    except ValueError:
        return None
    if expires_at.tzinfo is None or expires_at <= now:
        return None
    profile_text = pending.get("last_non_uuid_profile_text")
    return code, expires_at, profile_text if isinstance(profile_text, str) else None


def get_bilibili_last_profile_text(
    *, metadata_json: dict[str, Any] | None, account_identifier: str
) -> str | None:
    if not metadata_json:
        return None
    pending = metadata_json.get("bilibili_verification")
    if not isinstance(pending, dict):
        return None
    if pending.get("account_identifier") != account_identifier:
        return None
    profile_text = pending.get("last_non_uuid_profile_text")
    return profile_text if isinstance(profile_text, str) else None


def decode_bilibili_pending_confirmation_token(
    token: str,
) -> BilibiliVerificationPendingPayload:
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[security.ALGORITHM],
        )
        parsed = BilibiliVerificationPendingPayload.model_validate(payload)
    except (InvalidTokenError, ValidationError) as exc:
        raise ValueError("Invalid or expired Bilibili verification token") from exc

    if parsed.purpose != "bilibili_social_link_verify_pending":
        raise ValueError("Invalid Bilibili verification confirmation")
    return parsed


def build_bilibili_profile_url(*, account_identifier: str) -> str:
    return BILIBILI_PROFILE_URL.format(uid=account_identifier)


def parse_bilibili_profile_description(html_text: str) -> str | None:
    parser = _DescriptionMetaParser()
    parser.feed(html_text)
    parser.close()
    return parser.description


def parse_bilibili_profile_text(html_text: str) -> str | None:
    description = parse_bilibili_profile_description(html_text)
    if description is None:
        return None

    return _BILIBILI_DESCRIPTION_PREFIX_RE.sub("", description, count=1).strip()


async def fetch_bilibili_profile_text(*, account_identifier: str) -> str:
    response_text = await _fetch_bilibili_profile_html(
        account_identifier=account_identifier
    )
    profile_text = parse_bilibili_profile_text(response_text)
    if profile_text is None:
        raise BilibiliProfileFetchError(
            "Failed to read the Bilibili profile text. Try again later."
        )
    return profile_text


async def verify_bilibili_profile_contains_code(
    *,
    account_identifier: str,
    verification_code: str,
) -> None:
    profile_text = await fetch_bilibili_profile_text(
        account_identifier=account_identifier
    )
    if verification_code not in profile_text:
        raise BilibiliProfileVerificationCodeMissingError(
            "Verification code not found in the public Bilibili profile text."
        )


async def _fetch_bilibili_profile_html(*, account_identifier: str) -> str:
    profile_url = build_bilibili_profile_url(account_identifier=account_identifier)
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            headers=_bilibili_headers(),
            timeout=10.0,
        ) as client:
            response = await client.get(profile_url)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise BilibiliProfileFetchError(
            "Failed to fetch the Bilibili profile page. Try again later."
        ) from exc

    return response.text


def _build_bilibili_verification_code() -> str:
    return str(uuid.uuid4())
