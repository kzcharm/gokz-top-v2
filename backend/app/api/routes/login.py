import re
from datetime import timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from app import crud
from app.api.deps import CurrentUser, SessionDep
from app.core import security
from app.core.config import settings
from app.models import UserPublic

router = APIRouter(tags=["login"])

STEAM_OPENID_URL = "https://steamcommunity.com/openid/login"


@router.get("/login/steam")
async def login_steam(request: Request) -> RedirectResponse:
    """
    Initiate Steam OpenID authentication flow.
    Redirects user to Steam's login page.
    """
    base_url = str(request.base_url).rstrip("/")
    callback_path = f"{settings.API_V1_STR}/login/steam/callback"
    return_url = f"{base_url}{callback_path}"

    params = {
        "openid.ns": "http://specs.openid.net/auth/2.0",
        "openid.mode": "checkid_setup",
        "openid.return_to": return_url,
        "openid.realm": base_url,
        "openid.identity": "http://specs.openid.net/auth/2.0/identifier_select",
        "openid.claimed_id": "http://specs.openid.net/auth/2.0/identifier_select",
    }

    return RedirectResponse(url=f"{STEAM_OPENID_URL}?{urlencode(params)}")


@router.get("/login/steam/callback")
async def steam_callback(request: Request, session: SessionDep) -> RedirectResponse:
    """
    Handle Steam OpenID callback.
    Verifies the OpenID response and creates/updates user.
    Redirects to frontend with token in URL fragment.
    """
    query_params = dict(request.query_params)
    openid_mode = query_params.get("openid.mode")
    if openid_mode != "id_res":
        raise HTTPException(status_code=400, detail="Invalid OpenID mode")

    openid_claimed_id = query_params.get("openid.claimed_id")
    if not openid_claimed_id:
        raise HTTPException(status_code=400, detail="Missing OpenID claimed_id")

    match = re.search(r"https://steamcommunity.com/openid/id/(\d+)$", openid_claimed_id)
    if not match:
        raise HTTPException(status_code=400, detail="Invalid Steam ID format")
    steamid64 = int(match.group(1))

    openid_signed = query_params.get("openid.signed")
    openid_sig = query_params.get("openid.sig")
    if not openid_signed or not openid_sig:
        raise HTTPException(status_code=400, detail="Missing OpenID signature")

    verify_params = {
        "openid.ns": query_params.get("openid.ns", "http://specs.openid.net/auth/2.0"),
        "openid.mode": "check_authentication",
        "openid.op_endpoint": query_params.get("openid.op_endpoint"),
        "openid.claimed_id": query_params.get("openid.claimed_id"),
        "openid.identity": query_params.get("openid.identity"),
        "openid.return_to": query_params.get("openid.return_to"),
        "openid.response_nonce": query_params.get("openid.response_nonce"),
        "openid.assoc_handle": query_params.get("openid.assoc_handle"),
        "openid.signed": openid_signed,
        "openid.sig": openid_sig,
    }
    verify_params = {k: v for k, v in verify_params.items() if v}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(STEAM_OPENID_URL, data=verify_params)
            response.raise_for_status()
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail="Failed to verify OpenID response"
        ) from exc

    if "is_valid:true" not in response.text:
        raise HTTPException(status_code=400, detail="OpenID verification failed")

    user = await crud.get_or_create_user_from_steam(
        session=session,
        steamid64=steamid64,
    )
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    token = security.create_access_token(
        user.steamid64, expires_delta=access_token_expires
    )
    frontend_url = (
        f"{settings.FRONTEND_HOST.rstrip('/')}/auth/callback#access_token={token}"
    )
    return RedirectResponse(url=frontend_url)


@router.post("/login/test-token", response_model=UserPublic)
async def test_token(current_user: CurrentUser, session: SessionDep) -> Any:
    """
    Test access token
    """
    return await crud.to_user_public(session=session, user=current_user)
