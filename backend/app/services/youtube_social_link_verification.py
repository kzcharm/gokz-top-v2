from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
import jwt
from jwt.exceptions import InvalidTokenError
from pydantic import BaseModel, ValidationError

from app.core import security
from app.core.config import settings

GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
YOUTUBE_CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
YOUTUBE_OAUTH_SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
YOUTUBE_STATE_TTL = timedelta(minutes=10)
YOUTUBE_PENDING_CONFIRM_TTL = timedelta(minutes=10)


class YoutubeVerificationStatePayload(BaseModel):
    purpose: str
    mode: str
    steamid64: int
    link_id: str | None = None
    platform: str
    return_path: str
    exp: int


class YoutubeVerificationPendingPayload(BaseModel):
    purpose: str
    steamid64: int
    link_id: str
    platform: str
    authenticated_account_identifier: str
    authenticated_display_name: str
    current_account_identifier: str
    return_path: str
    exp: int


@dataclass(frozen=True, slots=True)
class YoutubeAuthenticatedChannel:
    account_identifier: str
    display_name: str
    matching_identifiers: frozenset[str]


def ensure_youtube_verification_configured() -> None:
    if not settings.YOUTUBE_CLIENT_ID or not settings.YOUTUBE_CLIENT_SECRET:
        raise ValueError("YouTube verification is not configured")


def create_youtube_verification_state_token(
    *,
    steamid64: int,
    return_path: str,
    mode: str,
    link_id: str | None = None,
) -> str:
    payload = YoutubeVerificationStatePayload(
        purpose="youtube_social_link_verify_state",
        mode=mode,
        steamid64=steamid64,
        link_id=link_id,
        platform="youtube",
        return_path=return_path,
        exp=_expiry_timestamp(YOUTUBE_STATE_TTL),
    )
    return jwt.encode(
        payload.model_dump(mode="json"),
        settings.SECRET_KEY,
        algorithm=security.ALGORITHM,
    )


def decode_youtube_verification_state_token(
    token: str,
) -> YoutubeVerificationStatePayload:
    payload = _decode_token(token, YoutubeVerificationStatePayload)
    if payload.purpose != "youtube_social_link_verify_state":
        raise ValueError("Invalid YouTube verification state")
    return payload


def create_youtube_pending_confirmation_token(
    *,
    steamid64: int,
    link_id: str,
    current_account_identifier: str,
    authenticated_channel: YoutubeAuthenticatedChannel,
    return_path: str,
) -> str:
    payload = YoutubeVerificationPendingPayload(
        purpose="youtube_social_link_verify_pending",
        steamid64=steamid64,
        link_id=link_id,
        platform="youtube",
        authenticated_account_identifier=authenticated_channel.account_identifier,
        authenticated_display_name=authenticated_channel.display_name,
        current_account_identifier=current_account_identifier,
        return_path=return_path,
        exp=_expiry_timestamp(YOUTUBE_PENDING_CONFIRM_TTL),
    )
    return jwt.encode(
        payload.model_dump(mode="json"),
        settings.SECRET_KEY,
        algorithm=security.ALGORITHM,
    )


def decode_youtube_pending_confirmation_token(
    token: str,
) -> YoutubeVerificationPendingPayload:
    payload = _decode_token(token, YoutubeVerificationPendingPayload)
    if payload.purpose != "youtube_social_link_verify_pending":
        raise ValueError("Invalid YouTube verification confirmation")
    return payload


def build_youtube_authorization_url(*, redirect_uri: str, state: str) -> str:
    ensure_youtube_verification_configured()
    client_id = settings.YOUTUBE_CLIENT_ID
    assert client_id is not None
    params = {
        "access_type": "online",
        "client_id": client_id,
        "include_granted_scopes": "true",
        "prompt": "select_account",
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": YOUTUBE_OAUTH_SCOPE,
        "state": state,
    }
    return f"{GOOGLE_AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_youtube_code_for_access_token(
    *, code: str, redirect_uri: str
) -> str:
    ensure_youtube_verification_configured()
    client_id = settings.YOUTUBE_CLIENT_ID
    client_secret = settings.YOUTUBE_CLIENT_SECRET
    assert client_id is not None
    assert client_secret is not None
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            },
        )
        response.raise_for_status()
    payload = response.json()
    access_token = payload.get("access_token")
    if not isinstance(access_token, str) or not access_token.strip():
        raise ValueError("YouTube token response did not include an access token")
    return access_token


async def fetch_youtube_authenticated_channels(
    *, access_token: str
) -> list[YoutubeAuthenticatedChannel]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            YOUTUBE_CHANNELS_URL,
            params={
                "part": "snippet",
                "mine": "true",
                "maxResults": 50,
            },
            headers={"Authorization": f"Bearer {access_token}"},
        )
        response.raise_for_status()
    payload = response.json()
    items = payload.get("items")
    if not isinstance(items, list):
        raise ValueError("YouTube channel response did not include channels")

    channels: list[YoutubeAuthenticatedChannel] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        channel_id = item.get("id")
        if not isinstance(channel_id, str) or not channel_id.strip():
            continue
        snippet = item.get("snippet")
        title = channel_id
        custom_url = None
        if isinstance(snippet, dict):
            snippet_title = snippet.get("title")
            if isinstance(snippet_title, str) and snippet_title.strip():
                title = snippet_title.strip()
            snippet_custom_url = snippet.get("customUrl")
            if isinstance(snippet_custom_url, str) and snippet_custom_url.strip():
                custom_url = snippet_custom_url.strip()

        identifiers = {f"channel/{channel_id.strip()}"}
        if custom_url is not None:
            normalized_custom_url = custom_url.lower()
            if normalized_custom_url.startswith("@"):
                identifiers.add(normalized_custom_url)
            else:
                identifiers.add(f"@{normalized_custom_url}")

        channels.append(
            YoutubeAuthenticatedChannel(
                account_identifier=f"channel/{channel_id.strip()}",
                display_name=title,
                matching_identifiers=frozenset(identifiers),
            )
        )

    return channels


def find_matching_youtube_channel(
    *,
    channels: list[YoutubeAuthenticatedChannel],
    account_identifier: str,
) -> YoutubeAuthenticatedChannel | None:
    normalized = account_identifier.lower()
    for channel in channels:
        matching_identifiers = {
            identifier.lower() for identifier in channel.matching_identifiers
        }
        if normalized in matching_identifiers:
            return channel
    return None


def build_youtube_verification_error_return_url(
    *,
    frontend_host: str,
    return_path: str,
    message: str,
) -> str:
    return _build_return_url(
        frontend_host=frontend_host,
        return_path=return_path,
        params={
            "youtubeVerification": "error",
            "message": message,
        },
    )


def build_youtube_verification_success_return_url(
    *,
    frontend_host: str,
    return_path: str,
) -> str:
    return _build_return_url(
        frontend_host=frontend_host,
        return_path=return_path,
        params={
            "youtubeVerification": "success",
        },
    )


def build_youtube_verification_mismatch_return_url(
    *,
    frontend_host: str,
    return_path: str,
    link_id: str,
    current_account_identifier: str,
    authenticated_account_identifier: str,
    authenticated_display_name: str,
    pending_token: str,
) -> str:
    return _build_return_url(
        frontend_host=frontend_host,
        return_path=return_path,
        params={
            "youtubeVerification": "mismatch",
            "youtubeAction": "verify",
            "linkId": link_id,
            "currentAccount": current_account_identifier,
            "authenticatedAccount": authenticated_account_identifier,
            "authenticatedDisplayName": authenticated_display_name,
            "pendingToken": pending_token,
        },
    )


def _build_return_url(
    *,
    frontend_host: str,
    return_path: str,
    params: dict[str, str],
) -> str:
    path = return_path if return_path.startswith("/") else "/settings"
    base = frontend_host.rstrip("/")
    query = urlencode(params)
    separator = "&" if "?" in path else "?"
    return f"{base}{path}{separator}{query}"


def _expiry_timestamp(ttl: timedelta) -> int:
    return int((datetime.now(UTC) + ttl).timestamp())


def _decode_token[TokenModel: BaseModel](
    token: str, model: type[TokenModel]
) -> TokenModel:
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[security.ALGORITHM],
        )
        return model.model_validate(payload)
    except (InvalidTokenError, ValidationError) as exc:
        raise ValueError("Invalid or expired YouTube verification token") from exc
