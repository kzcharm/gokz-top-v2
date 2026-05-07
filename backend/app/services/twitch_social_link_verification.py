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

TWITCH_AUTHORIZE_URL = "https://id.twitch.tv/oauth2/authorize"
TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
TWITCH_USERS_URL = "https://api.twitch.tv/helix/users"
TWITCH_STATE_TTL = timedelta(minutes=10)
TWITCH_PENDING_CONFIRM_TTL = timedelta(minutes=10)


class TwitchVerificationStatePayload(BaseModel):
    purpose: str
    steamid64: int
    link_id: str
    platform: str
    return_path: str
    exp: int


class TwitchVerificationPendingPayload(BaseModel):
    purpose: str
    steamid64: int
    link_id: str
    platform: str
    authenticated_account_identifier: str
    current_account_identifier: str
    return_path: str
    exp: int


@dataclass(frozen=True, slots=True)
class TwitchAuthenticatedUser:
    account_identifier: str
    display_name: str


def ensure_twitch_verification_configured() -> None:
    if not settings.TWITCH_CLIENT_ID or not settings.TWITCH_CLIENT_SECRET:
        raise ValueError("Twitch verification is not configured")


def create_twitch_verification_state_token(
    *,
    steamid64: int,
    link_id: str,
    return_path: str,
) -> str:
    payload = TwitchVerificationStatePayload(
        purpose="twitch_social_link_verify_state",
        steamid64=steamid64,
        link_id=link_id,
        platform="twitch",
        return_path=return_path,
        exp=_expiry_timestamp(TWITCH_STATE_TTL),
    )
    return jwt.encode(
        payload.model_dump(mode="json"),
        settings.SECRET_KEY,
        algorithm=security.ALGORITHM,
    )


def decode_twitch_verification_state_token(
    token: str,
) -> TwitchVerificationStatePayload:
    payload = _decode_token(token, TwitchVerificationStatePayload)
    if payload.purpose != "twitch_social_link_verify_state":
        raise ValueError("Invalid Twitch verification state")
    return payload


def create_twitch_pending_confirmation_token(
    *,
    steamid64: int,
    link_id: str,
    current_account_identifier: str,
    authenticated_account_identifier: str,
    return_path: str,
) -> str:
    payload = TwitchVerificationPendingPayload(
        purpose="twitch_social_link_verify_pending",
        steamid64=steamid64,
        link_id=link_id,
        platform="twitch",
        authenticated_account_identifier=authenticated_account_identifier,
        current_account_identifier=current_account_identifier,
        return_path=return_path,
        exp=_expiry_timestamp(TWITCH_PENDING_CONFIRM_TTL),
    )
    return jwt.encode(
        payload.model_dump(mode="json"),
        settings.SECRET_KEY,
        algorithm=security.ALGORITHM,
    )


def decode_twitch_pending_confirmation_token(
    token: str,
) -> TwitchVerificationPendingPayload:
    payload = _decode_token(token, TwitchVerificationPendingPayload)
    if payload.purpose != "twitch_social_link_verify_pending":
        raise ValueError("Invalid Twitch verification confirmation")
    return payload


def build_twitch_authorization_url(*, redirect_uri: str, state: str) -> str:
    ensure_twitch_verification_configured()
    client_id = settings.TWITCH_CLIENT_ID
    assert client_id is not None
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "",
        "state": state,
    }
    return f"{TWITCH_AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_twitch_code_for_access_token(
    *, code: str, redirect_uri: str
) -> str:
    ensure_twitch_verification_configured()
    client_id = settings.TWITCH_CLIENT_ID
    client_secret = settings.TWITCH_CLIENT_SECRET
    assert client_id is not None
    assert client_secret is not None
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            TWITCH_TOKEN_URL,
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
        raise ValueError("Twitch token response did not include an access token")
    return access_token


async def fetch_twitch_authenticated_user(
    *, access_token: str
) -> TwitchAuthenticatedUser:
    ensure_twitch_verification_configured()
    client_id = settings.TWITCH_CLIENT_ID
    assert client_id is not None
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            TWITCH_USERS_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Client-Id": client_id,
            },
        )
        response.raise_for_status()
    payload = response.json()
    data = payload.get("data")
    if not isinstance(data, list) or len(data) == 0:
        raise ValueError("Twitch user response did not include a user")
    user = data[0]
    login = user.get("login")
    display_name = user.get("display_name")
    if not isinstance(login, str) or not login.strip():
        raise ValueError("Twitch user response did not include a login")
    if not isinstance(display_name, str) or not display_name.strip():
        display_name = login
    return TwitchAuthenticatedUser(
        account_identifier=login.strip().lower(),
        display_name=display_name.strip(),
    )


def build_twitch_verification_error_return_url(
    *,
    frontend_host: str,
    return_path: str,
    message: str,
) -> str:
    return _build_return_url(
        frontend_host=frontend_host,
        return_path=return_path,
        params={
            "tab": "social-links",
            "twitchVerification": "error",
            "message": message,
        },
    )


def build_twitch_verification_success_return_url(
    *,
    frontend_host: str,
    return_path: str,
) -> str:
    return _build_return_url(
        frontend_host=frontend_host,
        return_path=return_path,
        params={
            "tab": "social-links",
            "twitchVerification": "success",
        },
    )


def build_twitch_verification_mismatch_return_url(
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
            "tab": "social-links",
            "twitchVerification": "mismatch",
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
    return f"{base}{path}?{query}"


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
        raise ValueError("Invalid or expired Twitch verification token") from exc
