import uuid

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from app import crud
from app.api.deps import CurrentUser, SessionDep
from app.api.v1.player_api_helpers import (
    ensure_current_user_owns_social_link,
    ensure_link_is_bilibili_and_unverified,
    ensure_link_is_twitch_and_unverified,
    ensure_link_is_youtube_and_unverified,
    get_player_or_404,
    settings_return_path,
    twitch_callback_url,
    twitch_return_path,
    youtube_callback_url,
    youtube_return_path,
)
from app.core.config import settings
from app.models import (
    PlayerSocialLinkBilibiliVerificationStart,
    PlayerSocialLinkCreate,
    PlayerSocialLinksPublic,
    PlayerSocialLinkUpdate,
    PlayerSocialLinkVerifyConfirm,
    PlayerSocialPlatform,
)
from app.services.bilibili_social_link_verification import (
    BilibiliProfileFetchError,
    BilibiliProfileVerificationCodeMissingError,
    build_bilibili_profile_url,
    create_bilibili_pending_confirmation_token,
    decode_bilibili_pending_confirmation_token,
    fetch_bilibili_profile_text,
    verify_bilibili_profile_contains_code,
)
from app.services.twitch_social_link_verification import (
    build_twitch_authorization_url,
    build_twitch_verification_error_return_url,
    build_twitch_verification_mismatch_return_url,
    build_twitch_verification_success_return_url,
    create_twitch_pending_confirmation_token,
    create_twitch_verification_state_token,
    decode_twitch_pending_confirmation_token,
    decode_twitch_verification_state_token,
    ensure_twitch_verification_configured,
    exchange_twitch_code_for_access_token,
    fetch_twitch_authenticated_user,
)
from app.services.youtube_social_link_verification import (
    build_youtube_authorization_url,
    build_youtube_verification_error_return_url,
    build_youtube_verification_mismatch_return_url,
    build_youtube_verification_success_return_url,
    create_youtube_pending_confirmation_token,
    create_youtube_verification_state_token,
    decode_youtube_pending_confirmation_token,
    decode_youtube_verification_state_token,
    ensure_youtube_verification_configured,
    exchange_youtube_code_for_access_token,
    fetch_youtube_authenticated_channels,
    find_matching_youtube_channel,
)

router = APIRouter(prefix="/player-social-links", tags=["player-social-links"])
verification_router = APIRouter(
    prefix="/social-link-verifications",
    tags=["player-social-links"],
)


@router.get("/players/{identifier:path}", response_model=PlayerSocialLinksPublic)
async def read_player_social_links(
    identifier: str,
    session: SessionDep,
) -> PlayerSocialLinksPublic:
    player = await get_player_or_404(session=session, identifier=identifier)
    links = await crud.list_player_social_links(
        session=session,
        player_steamid64=player.steamid64,
    )
    return PlayerSocialLinksPublic(
        data=crud.to_player_social_link_publics(links=links),
        count=len(links),
    )


@router.post("/me/social-links", response_model=PlayerSocialLinksPublic)
async def create_player_social_link(
    body: PlayerSocialLinkCreate,
    session: SessionDep,
    current_user: CurrentUser,
) -> PlayerSocialLinksPublic:
    try:
        await crud.create_player_social_link(
            session=session,
            player_steamid64=current_user.steamid64,
            url=body.url,
            verified=False,
        )
    except crud.PlayerSocialLinkConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    links = await crud.list_player_social_links(
        session=session,
        player_steamid64=current_user.steamid64,
    )
    return PlayerSocialLinksPublic(
        data=crud.to_player_social_link_publics(links=links),
        count=len(links),
    )


@router.patch("/me/social-links/{link_id}", response_model=PlayerSocialLinksPublic)
async def update_player_social_link(
    link_id: uuid.UUID,
    body: PlayerSocialLinkUpdate,
    session: SessionDep,
    current_user: CurrentUser,
) -> PlayerSocialLinksPublic:
    link = await crud.get_player_social_link(session=session, id=link_id)
    if link is None:
        raise HTTPException(status_code=404, detail="Social link not found")
    ensure_current_user_owns_social_link(
        current_user=current_user,
        target_steamid64=link.player_steamid64,
    )

    try:
        await crud.update_player_social_link(
            session=session,
            link=link,
            url=body.url,
        )
    except crud.PlayerSocialLinkConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    links = await crud.list_player_social_links(
        session=session,
        player_steamid64=current_user.steamid64,
    )
    return PlayerSocialLinksPublic(
        data=crud.to_player_social_link_publics(links=links),
        count=len(links),
    )


@router.delete("/me/social-links/{link_id}", response_model=PlayerSocialLinksPublic)
async def delete_player_social_link(
    link_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> PlayerSocialLinksPublic:
    link = await crud.get_player_social_link(session=session, id=link_id)
    if link is None:
        raise HTTPException(status_code=404, detail="Social link not found")
    ensure_current_user_owns_social_link(
        current_user=current_user,
        target_steamid64=link.player_steamid64,
    )

    await crud.delete_player_social_link(session=session, link=link)
    links = await crud.list_player_social_links(
        session=session,
        player_steamid64=current_user.steamid64,
    )
    return PlayerSocialLinksPublic(
        data=crud.to_player_social_link_publics(links=links),
        count=len(links),
    )


@router.post("/me/social-links/{link_id}/twitch-verification-requests")
async def start_player_twitch_social_link_verification(
    link_id: uuid.UUID,
    request: Request,
    session: SessionDep,
    current_user: CurrentUser,
) -> dict[str, str]:
    link = await crud.get_player_social_link(session=session, id=link_id)
    if link is None:
        raise HTTPException(status_code=404, detail="Social link not found")
    ensure_current_user_owns_social_link(
        current_user=current_user,
        target_steamid64=link.player_steamid64,
    )
    ensure_link_is_twitch_and_unverified(link=link)

    try:
        ensure_twitch_verification_configured()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    state = create_twitch_verification_state_token(
        steamid64=link.player_steamid64,
        link_id=str(link.id),
        return_path=twitch_return_path(),
        mode="verify",
    )
    authorization_url = build_twitch_authorization_url(
        redirect_uri=twitch_callback_url(request),
        state=state,
    )
    return {"authorization_url": authorization_url}


@router.post("/me/social-links/twitch/connection-requests")
async def start_player_twitch_social_link_add(
    request: Request,
    session: SessionDep,
    current_user: CurrentUser,
) -> dict[str, str]:
    existing_links = await crud.list_player_social_links(
        session=session,
        player_steamid64=current_user.steamid64,
    )
    if any(link.platform == PlayerSocialPlatform.TWITCH for link in existing_links):
        raise HTTPException(
            status_code=409,
            detail="A Twitch social link already exists for this player",
        )

    try:
        ensure_twitch_verification_configured()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    state = create_twitch_verification_state_token(
        steamid64=current_user.steamid64,
        return_path=twitch_return_path(),
        mode="add",
    )
    authorization_url = build_twitch_authorization_url(
        redirect_uri=twitch_callback_url(request),
        state=state,
    )
    return {"authorization_url": authorization_url}


@verification_router.get("/twitch/callback")
async def complete_player_twitch_social_link_verification(
    request: Request,
    session: SessionDep,
    state: str,
    code: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
) -> RedirectResponse:
    frontend_host = settings.FRONTEND_HOST
    try:
        decoded_state = decode_twitch_verification_state_token(state)
    except ValueError as exc:
        return RedirectResponse(
            url=build_twitch_verification_error_return_url(
                frontend_host=frontend_host,
                return_path=settings_return_path(),
                message=str(exc),
            )
        )

    if error is not None:
        message = error_description or error
        return RedirectResponse(
            url=build_twitch_verification_error_return_url(
                frontend_host=frontend_host,
                return_path=decoded_state.return_path,
                message=f"Twitch verification failed: {message}",
            )
        )

    if not code:
        return RedirectResponse(
            url=build_twitch_verification_error_return_url(
                frontend_host=frontend_host,
                return_path=decoded_state.return_path,
                message="Twitch verification did not return an authorization code",
            )
        )

    try:
        access_token = await exchange_twitch_code_for_access_token(
            code=code,
            redirect_uri=twitch_callback_url(request),
        )
        twitch_user = await fetch_twitch_authenticated_user(access_token=access_token)
    except (ValueError, httpx.HTTPError) as exc:
        return RedirectResponse(
            url=build_twitch_verification_error_return_url(
                frontend_host=frontend_host,
                return_path=decoded_state.return_path,
                message=f"Failed to verify Twitch account: {exc}",
            )
        )

    if decoded_state.mode == "add":
        try:
            await crud.create_player_social_link(
                session=session,
                player_steamid64=decoded_state.steamid64,
                url=f"https://www.twitch.tv/{twitch_user.account_identifier}",
                verified=True,
            )
        except crud.PlayerSocialLinkConflictError as exc:
            return RedirectResponse(
                url=build_twitch_verification_error_return_url(
                    frontend_host=frontend_host,
                    return_path=decoded_state.return_path,
                    message=str(exc),
                )
            )
        except ValueError as exc:
            return RedirectResponse(
                url=build_twitch_verification_error_return_url(
                    frontend_host=frontend_host,
                    return_path=decoded_state.return_path,
                    message=str(exc),
                )
            )
        return RedirectResponse(
            url=build_twitch_verification_success_return_url(
                frontend_host=frontend_host,
                return_path=decoded_state.return_path,
            )
        )

    try:
        link_id = uuid.UUID(decoded_state.link_id or "")
    except ValueError:
        return RedirectResponse(
            url=build_twitch_verification_error_return_url(
                frontend_host=frontend_host,
                return_path=decoded_state.return_path,
                message="Invalid Twitch verification link",
            )
        )

    link = await crud.get_player_social_link(session=session, id=link_id)
    if link is None or link.player_steamid64 != decoded_state.steamid64:
        return RedirectResponse(
            url=build_twitch_verification_error_return_url(
                frontend_host=frontend_host,
                return_path=decoded_state.return_path,
                message="Social link not found",
            )
        )

    try:
        ensure_link_is_twitch_and_unverified(link=link)
    except HTTPException as exc:
        return RedirectResponse(
            url=build_twitch_verification_error_return_url(
                frontend_host=frontend_host,
                return_path=decoded_state.return_path,
                message=str(exc.detail),
            )
        )

    if link.account_identifier == twitch_user.account_identifier:
        try:
            await crud.update_player_social_link(
                session=session,
                link=link,
                verified=True,
            )
        except crud.PlayerSocialLinkConflictError as exc:
            return RedirectResponse(
                url=build_twitch_verification_error_return_url(
                    frontend_host=frontend_host,
                    return_path=decoded_state.return_path,
                    message=str(exc),
                )
            )
        return RedirectResponse(
            url=build_twitch_verification_success_return_url(
                frontend_host=frontend_host,
                return_path=decoded_state.return_path,
            )
        )

    pending_token = create_twitch_pending_confirmation_token(
        steamid64=decoded_state.steamid64,
        link_id=str(link.id),
        current_account_identifier=link.account_identifier,
        authenticated_account_identifier=twitch_user.account_identifier,
        return_path=decoded_state.return_path,
    )
    return RedirectResponse(
        url=build_twitch_verification_mismatch_return_url(
            frontend_host=frontend_host,
            return_path=decoded_state.return_path,
            link_id=str(link.id),
            current_account_identifier=link.account_identifier,
            authenticated_account_identifier=twitch_user.account_identifier,
            authenticated_display_name=twitch_user.display_name,
            pending_token=pending_token,
        )
    )


@router.post(
    "/me/social-links/{link_id}/twitch-verification-confirmations",
    response_model=PlayerSocialLinksPublic,
)
async def confirm_player_twitch_social_link_verification(
    link_id: uuid.UUID,
    body: PlayerSocialLinkVerifyConfirm,
    session: SessionDep,
    current_user: CurrentUser,
) -> PlayerSocialLinksPublic:
    link = await crud.get_player_social_link(session=session, id=link_id)
    if link is None:
        raise HTTPException(status_code=404, detail="Social link not found")
    ensure_current_user_owns_social_link(
        current_user=current_user,
        target_steamid64=link.player_steamid64,
    )
    ensure_link_is_twitch_and_unverified(link=link)

    try:
        pending = decode_twitch_pending_confirmation_token(body.pending_token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if (
        pending.steamid64 != link.player_steamid64
        or pending.link_id != str(link.id)
        or pending.platform != "twitch"
    ):
        raise HTTPException(
            status_code=400,
            detail="Twitch verification confirmation does not match this social link",
        )

    if link.account_identifier != pending.current_account_identifier:
        raise HTTPException(
            status_code=409,
            detail="Social link changed during Twitch verification; start again",
        )

    try:
        await crud.update_player_social_link(
            session=session,
            link=link,
            url=f"https://www.twitch.tv/{pending.authenticated_account_identifier}",
            verified=True,
        )
    except crud.PlayerSocialLinkConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    links = await crud.list_player_social_links(
        session=session,
        player_steamid64=current_user.steamid64,
    )
    return PlayerSocialLinksPublic(
        data=crud.to_player_social_link_publics(links=links),
        count=len(links),
    )


@router.post("/me/social-links/{link_id}/youtube-verification-requests")
async def start_player_youtube_social_link_verification(
    link_id: uuid.UUID,
    request: Request,
    session: SessionDep,
    current_user: CurrentUser,
) -> dict[str, str]:
    link = await crud.get_player_social_link(session=session, id=link_id)
    if link is None:
        raise HTTPException(status_code=404, detail="Social link not found")
    ensure_current_user_owns_social_link(
        current_user=current_user,
        target_steamid64=link.player_steamid64,
    )
    ensure_link_is_youtube_and_unverified(link=link)

    try:
        ensure_youtube_verification_configured()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    state = create_youtube_verification_state_token(
        steamid64=link.player_steamid64,
        link_id=str(link.id),
        return_path=youtube_return_path(),
        mode="verify",
    )
    authorization_url = build_youtube_authorization_url(
        redirect_uri=youtube_callback_url(request),
        state=state,
    )
    return {"authorization_url": authorization_url}


@router.post("/me/social-links/youtube/connection-requests")
async def start_player_youtube_social_link_add(
    request: Request,
    session: SessionDep,
    current_user: CurrentUser,
) -> dict[str, str]:
    existing_links = await crud.list_player_social_links(
        session=session,
        player_steamid64=current_user.steamid64,
    )
    if any(link.platform == PlayerSocialPlatform.YOUTUBE for link in existing_links):
        raise HTTPException(
            status_code=409,
            detail="A YouTube social link already exists for this player",
        )

    try:
        ensure_youtube_verification_configured()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    state = create_youtube_verification_state_token(
        steamid64=current_user.steamid64,
        return_path=youtube_return_path(),
        mode="add",
    )
    authorization_url = build_youtube_authorization_url(
        redirect_uri=youtube_callback_url(request),
        state=state,
    )
    return {"authorization_url": authorization_url}


@verification_router.get("/youtube/callback")
async def complete_player_youtube_social_link_verification(
    request: Request,
    session: SessionDep,
    state: str,
    code: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
) -> RedirectResponse:
    frontend_host = settings.FRONTEND_HOST
    try:
        decoded_state = decode_youtube_verification_state_token(state)
    except ValueError as exc:
        return RedirectResponse(
            url=build_youtube_verification_error_return_url(
                frontend_host=frontend_host,
                return_path=settings_return_path(),
                message=str(exc),
            )
        )

    if error is not None:
        message = error_description or error
        return RedirectResponse(
            url=build_youtube_verification_error_return_url(
                frontend_host=frontend_host,
                return_path=decoded_state.return_path,
                message=f"YouTube verification failed: {message}",
            )
        )

    if not code:
        return RedirectResponse(
            url=build_youtube_verification_error_return_url(
                frontend_host=frontend_host,
                return_path=decoded_state.return_path,
                message="YouTube verification did not return an authorization code",
            )
        )

    try:
        access_token = await exchange_youtube_code_for_access_token(
            code=code,
            redirect_uri=youtube_callback_url(request),
        )
        youtube_channels = await fetch_youtube_authenticated_channels(
            access_token=access_token
        )
    except (ValueError, httpx.HTTPError) as exc:
        return RedirectResponse(
            url=build_youtube_verification_error_return_url(
                frontend_host=frontend_host,
                return_path=decoded_state.return_path,
                message=f"Failed to verify YouTube account: {exc}",
            )
        )

    if not youtube_channels:
        return RedirectResponse(
            url=build_youtube_verification_error_return_url(
                frontend_host=frontend_host,
                return_path=decoded_state.return_path,
                message="No YouTube channel was found for the authenticated account",
            )
        )

    if decoded_state.mode == "add":
        if len(youtube_channels) != 1:
            return RedirectResponse(
                url=build_youtube_verification_error_return_url(
                    frontend_host=frontend_host,
                    return_path=decoded_state.return_path,
                    message=(
                        "Multiple YouTube channels were found. Add the exact "
                        "channel URL first, then verify it."
                    ),
                )
            )
        channel = youtube_channels[0]
        try:
            await crud.create_player_social_link(
                session=session,
                player_steamid64=decoded_state.steamid64,
                url=f"https://www.youtube.com/{channel.account_identifier}",
                verified=True,
            )
        except crud.PlayerSocialLinkConflictError as exc:
            return RedirectResponse(
                url=build_youtube_verification_error_return_url(
                    frontend_host=frontend_host,
                    return_path=decoded_state.return_path,
                    message=str(exc),
                )
            )
        except ValueError as exc:
            return RedirectResponse(
                url=build_youtube_verification_error_return_url(
                    frontend_host=frontend_host,
                    return_path=decoded_state.return_path,
                    message=str(exc),
                )
            )
        return RedirectResponse(
            url=build_youtube_verification_success_return_url(
                frontend_host=frontend_host,
                return_path=decoded_state.return_path,
            )
        )

    try:
        link_id = uuid.UUID(decoded_state.link_id or "")
    except ValueError:
        return RedirectResponse(
            url=build_youtube_verification_error_return_url(
                frontend_host=frontend_host,
                return_path=decoded_state.return_path,
                message="Invalid YouTube verification link",
            )
        )

    link = await crud.get_player_social_link(session=session, id=link_id)
    if link is None or link.player_steamid64 != decoded_state.steamid64:
        return RedirectResponse(
            url=build_youtube_verification_error_return_url(
                frontend_host=frontend_host,
                return_path=decoded_state.return_path,
                message="Social link not found",
            )
        )

    try:
        ensure_link_is_youtube_and_unverified(link=link)
    except HTTPException as exc:
        return RedirectResponse(
            url=build_youtube_verification_error_return_url(
                frontend_host=frontend_host,
                return_path=decoded_state.return_path,
                message=str(exc.detail),
            )
        )

    matching_channel = find_matching_youtube_channel(
        channels=youtube_channels,
        account_identifier=link.account_identifier,
    )
    if matching_channel is not None:
        try:
            await crud.update_player_social_link(
                session=session,
                link=link,
                url=f"https://www.youtube.com/{matching_channel.account_identifier}",
                verified=True,
            )
        except crud.PlayerSocialLinkConflictError as exc:
            return RedirectResponse(
                url=build_youtube_verification_error_return_url(
                    frontend_host=frontend_host,
                    return_path=decoded_state.return_path,
                    message=str(exc),
                )
            )
        return RedirectResponse(
            url=build_youtube_verification_success_return_url(
                frontend_host=frontend_host,
                return_path=decoded_state.return_path,
            )
        )

    if len(youtube_channels) != 1:
        return RedirectResponse(
            url=build_youtube_verification_error_return_url(
                frontend_host=frontend_host,
                return_path=decoded_state.return_path,
                message=(
                    "Multiple YouTube channels were found and none matched this "
                    "link. Add the exact channel URL first, then verify it."
                ),
            )
        )

    authenticated_channel = youtube_channels[0]
    pending_token = create_youtube_pending_confirmation_token(
        steamid64=decoded_state.steamid64,
        link_id=str(link.id),
        current_account_identifier=link.account_identifier,
        authenticated_channel=authenticated_channel,
        return_path=decoded_state.return_path,
    )
    return RedirectResponse(
        url=build_youtube_verification_mismatch_return_url(
            frontend_host=frontend_host,
            return_path=decoded_state.return_path,
            link_id=str(link.id),
            current_account_identifier=link.account_identifier,
            authenticated_account_identifier=authenticated_channel.account_identifier,
            authenticated_display_name=authenticated_channel.display_name,
            pending_token=pending_token,
        )
    )


@router.post(
    "/me/social-links/{link_id}/youtube-verification-confirmations",
    response_model=PlayerSocialLinksPublic,
)
async def confirm_player_youtube_social_link_verification(
    link_id: uuid.UUID,
    body: PlayerSocialLinkVerifyConfirm,
    session: SessionDep,
    current_user: CurrentUser,
) -> PlayerSocialLinksPublic:
    link = await crud.get_player_social_link(session=session, id=link_id)
    if link is None:
        raise HTTPException(status_code=404, detail="Social link not found")
    ensure_current_user_owns_social_link(
        current_user=current_user,
        target_steamid64=link.player_steamid64,
    )
    ensure_link_is_youtube_and_unverified(link=link)

    try:
        pending = decode_youtube_pending_confirmation_token(body.pending_token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if (
        pending.steamid64 != link.player_steamid64
        or pending.link_id != str(link.id)
        or pending.platform != "youtube"
    ):
        raise HTTPException(
            status_code=400,
            detail="YouTube verification confirmation does not match this social link",
        )

    if link.account_identifier != pending.current_account_identifier:
        raise HTTPException(
            status_code=409,
            detail="Social link changed during YouTube verification; start again",
        )

    try:
        await crud.update_player_social_link(
            session=session,
            link=link,
            url=f"https://www.youtube.com/{pending.authenticated_account_identifier}",
            verified=True,
        )
    except crud.PlayerSocialLinkConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    links = await crud.list_player_social_links(
        session=session,
        player_steamid64=current_user.steamid64,
    )
    return PlayerSocialLinksPublic(
        data=crud.to_player_social_link_publics(links=links),
        count=len(links),
    )


@router.post(
    "/me/social-links/{link_id}/bilibili-verification-requests",
    response_model=PlayerSocialLinkBilibiliVerificationStart,
)
async def start_player_bilibili_social_link_verification(
    link_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> PlayerSocialLinkBilibiliVerificationStart:
    link = await crud.get_player_social_link(session=session, id=link_id)
    if link is None:
        raise HTTPException(status_code=404, detail="Social link not found")
    ensure_current_user_owns_social_link(
        current_user=current_user,
        target_steamid64=link.player_steamid64,
    )
    ensure_link_is_bilibili_and_unverified(link=link)

    pending_token, verification_code, expires_at = (
        create_bilibili_pending_confirmation_token(
            steamid64=link.player_steamid64,
            link_id=str(link.id),
            current_account_identifier=link.account_identifier,
        )
    )
    try:
        current_profile_text = await fetch_bilibili_profile_text(
            account_identifier=link.account_identifier
        )
    except BilibiliProfileFetchError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return PlayerSocialLinkBilibiliVerificationStart(
        pending_token=pending_token,
        verification_code=verification_code,
        profile_url=build_bilibili_profile_url(
            account_identifier=link.account_identifier
        ),
        current_profile_text=current_profile_text,
        expires_at=expires_at,
    )


@router.post(
    "/me/social-links/{link_id}/bilibili-verification-confirmations",
    response_model=PlayerSocialLinksPublic,
)
async def confirm_player_bilibili_social_link_verification(
    link_id: uuid.UUID,
    body: PlayerSocialLinkVerifyConfirm,
    session: SessionDep,
    current_user: CurrentUser,
) -> PlayerSocialLinksPublic:
    link = await crud.get_player_social_link(session=session, id=link_id)
    if link is None:
        raise HTTPException(status_code=404, detail="Social link not found")
    ensure_current_user_owns_social_link(
        current_user=current_user,
        target_steamid64=link.player_steamid64,
    )
    ensure_link_is_bilibili_and_unverified(link=link)

    try:
        pending = decode_bilibili_pending_confirmation_token(body.pending_token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if (
        pending.steamid64 != link.player_steamid64
        or pending.link_id != str(link.id)
        or pending.platform != "bilibili"
    ):
        raise HTTPException(
            status_code=400,
            detail="Bilibili verification confirmation does not match this social link",
        )

    if link.account_identifier != pending.current_account_identifier:
        raise HTTPException(
            status_code=409,
            detail="Social link changed during Bilibili verification; start again",
        )

    try:
        await verify_bilibili_profile_contains_code(
            account_identifier=link.account_identifier,
            verification_code=pending.verification_code,
        )
    except BilibiliProfileVerificationCodeMissingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except BilibiliProfileFetchError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        await crud.update_player_social_link(
            session=session,
            link=link,
            verified=True,
        )
    except crud.PlayerSocialLinkConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    links = await crud.list_player_social_links(
        session=session,
        player_steamid64=current_user.steamid64,
    )
    return PlayerSocialLinksPublic(
        data=crud.to_player_social_link_publics(links=links),
        count=len(links),
    )
