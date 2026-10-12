import secrets
from urllib.parse import urlencode, urlsplit

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from app import crud
from app.api.deps import CurrentUser, SessionDep
from app.core.config import settings
from app.models import PlayerSocialPlatform
from app.services.discord_social_link_verification import (
    DISCORD_STATE_COOKIE,
    DISCORD_STATE_TTL_SECONDS,
    build_discord_authorization_url,
    create_discord_state,
    decode_discord_state,
    discord_callback_url,
    ensure_discord_configured,
    fetch_discord_account_identifier,
)

router = APIRouter(tags=["player-social-links"])


@router.post("/player-social-links/me/social-links/discord/connection-requests")
async def start_discord_connection(
    response: Response, session: SessionDep, current_user: CurrentUser
) -> dict[str, str]:
    links = await crud.list_player_social_links(
        session=session, player_steamid64=current_user.steamid64
    )
    if any(link.platform == PlayerSocialPlatform.DISCORD for link in links):
        raise HTTPException(
            status_code=409, detail="A Discord account is already linked"
        )
    try:
        ensure_discord_configured()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    nonce = secrets.token_urlsafe(32)
    state = create_discord_state(steamid64=current_user.steamid64, nonce=nonce)
    response.set_cookie(
        DISCORD_STATE_COOKIE,
        nonce,
        max_age=DISCORD_STATE_TTL_SECONDS,
        path=urlsplit(discord_callback_url()).path,
        secure=discord_callback_url().startswith("https://"),
        httponly=True,
        samesite="lax",
    )
    response.headers["Cache-Control"] = "no-store"
    return {"authorization_url": build_discord_authorization_url(state=state)}


def _return_to_settings(*, message: str | None = None) -> RedirectResponse:
    params = {"discordVerification": "error" if message else "success"}
    if message:
        params["message"] = message
    response = RedirectResponse(
        f"{settings.FRONTEND_HOST.rstrip('/')}/settings/social-links?{urlencode(params)}",
        status_code=303,
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )
    response.delete_cookie(
        DISCORD_STATE_COOKIE,
        path=urlsplit(discord_callback_url()).path,
        secure=discord_callback_url().startswith("https://"),
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/social-link-verifications/discord/callback", include_in_schema=False)
async def complete_discord_connection(
    request: Request,
    session: SessionDep,
    state: str = "",
    code: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    try:
        payload = decode_discord_state(state)
        cookie_nonce = request.cookies.get(DISCORD_STATE_COOKIE, "")
        if (
            not cookie_nonce
            or not cookie_nonce.isascii()
            or not secrets.compare_digest(cookie_nonce, payload.nonce)
        ):
            raise ValueError("Invalid Discord connection session; start again")
    except ValueError as exc:
        return _return_to_settings(message=str(exc))
    if error:
        return _return_to_settings(
            message="Discord authorization was declined; try again"
        )
    if not code:
        return _return_to_settings(
            message="Discord did not return an authorization code"
        )
    try:
        account_id = await fetch_discord_account_identifier(code=code)
    except (ValueError, httpx.HTTPError):
        # Never expose provider response bodies, codes, or tokens in redirects.
        return _return_to_settings(
            message="Unable to verify your Discord account; try again"
        )
    try:
        await crud.create_player_social_link(
            session=session,
            player_steamid64=payload.steamid64,
            url=f"https://discord.com/users/{account_id}",
            verified=True,
        )
    except crud.PlayerSocialLinkConflictError:
        return _return_to_settings(
            message="This player or Discord account already has a Discord link"
        )
    except ValueError:
        return _return_to_settings(
            message="Unable to link your Discord account; try again"
        )
    return _return_to_settings()
