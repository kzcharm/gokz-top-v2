from datetime import UTC, datetime, timedelta
from typing import Literal
from urllib.parse import urlencode

import httpx
import jwt
from jwt.exceptions import InvalidTokenError
from pydantic import BaseModel, Field, ValidationError

from app.core import security
from app.core.config import settings

DISCORD_STATE_COOKIE = "discord_social_link_state"
DISCORD_STATE_TTL_SECONDS = 600


class DiscordVerificationState(BaseModel):
    purpose: Literal["discord_social_link_connection"]
    steamid64: int
    nonce: str = Field(min_length=32, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    exp: int


def ensure_discord_configured() -> None:
    if not settings.DISCORD_CLIENT_ID or not settings.DISCORD_CLIENT_SECRET:
        raise ValueError("Discord linking is not configured")


def discord_callback_url() -> str:
    return (
        f"{settings.BACKEND_PUBLIC_URL.rstrip('/')}{settings.API_V1_STR}"
        "/social-link-verifications/discord/callback"
    )


def create_discord_state(*, steamid64: int, nonce: str) -> str:
    payload = DiscordVerificationState(
        purpose="discord_social_link_connection",
        steamid64=steamid64,
        nonce=nonce,
        exp=int(
            (
                datetime.now(UTC) + timedelta(seconds=DISCORD_STATE_TTL_SECONDS)
            ).timestamp()
        ),
    )
    return jwt.encode(
        payload.model_dump(), settings.SECRET_KEY, algorithm=security.ALGORITHM
    )


def decode_discord_state(state: str) -> DiscordVerificationState:
    try:
        return DiscordVerificationState.model_validate(
            jwt.decode(state, settings.SECRET_KEY, algorithms=[security.ALGORITHM])
        )
    except (InvalidTokenError, ValidationError) as exc:
        raise ValueError("Invalid or expired Discord connection; start again") from exc


def build_discord_authorization_url(*, state: str) -> str:
    ensure_discord_configured()
    return "https://discord.com/oauth2/authorize?" + urlencode(
        {
            "client_id": settings.DISCORD_CLIENT_ID,
            "response_type": "code",
            "redirect_uri": discord_callback_url(),
            "scope": "identify",
            "state": state,
            "prompt": "consent",
        }
    )


async def fetch_discord_account_identifier(*, code: str) -> str:
    ensure_discord_configured()
    async with httpx.AsyncClient(timeout=10.0) as client:
        token_response = await client.post(
            "https://discord.com/api/oauth2/token",
            data={
                "client_id": settings.DISCORD_CLIENT_ID,
                "client_secret": settings.DISCORD_CLIENT_SECRET,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": discord_callback_url(),
            },
        )
        token_response.raise_for_status()
        token_payload = token_response.json()
        access_token = (
            token_payload.get("access_token")
            if isinstance(token_payload, dict)
            else None
        )
        if not isinstance(access_token, str) or not access_token.strip():
            raise ValueError("Discord did not return an access token")
        user_response = await client.get(
            "https://discord.com/api/v10/users/@me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        user_response.raise_for_status()
    user_payload = user_response.json()
    account_id = user_payload.get("id") if isinstance(user_payload, dict) else None
    if (
        not isinstance(account_id, str)
        or not account_id.isascii()
        or not account_id.isdecimal()
        or not 0 < int(account_id) < 2**64
        or str(int(account_id)) != account_id
    ):
        raise ValueError("Discord did not return a valid user ID")
    return account_id
