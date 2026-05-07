import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse

from app import crud
from app.api.deps import (
    CurrentUser,
    OptionalCurrentUser,
    SessionDep,
    get_current_active_superuser,
    get_current_user,
)
from app.core.config import settings
from app.crud import player as player_crud
from app.models import (
    ModeScope,
    Player,
    PlayerBanStatusCheckPublic,
    PlayerFollowListQuery,
    PlayerFollowSummaryPublic,
    PlayerPinnedRecordsPublic,
    PlayerPinnedRecordUpsert,
    PlayerProfileViewsPublic,
    PlayerPublic,
    PlayersBatchPublic,
    PlayersBatchRead,
    PlayerSearchQuery,
    PlayerSettingsPublic,
    PlayerSettingsUpdate,
    PlayersListQuery,
    PlayerSocialLinkCreate,
    PlayerSocialLinksPublic,
    PlayerSocialLinkUpdate,
    PlayerSocialLinkVerifyConfirm,
    PlayerSocialPlatform,
    PlayersPublic,
    PlayerStatsPublic,
    PlayerStatType,
    PlayerUpdate,
    RecordType,
    User,
)
from app.services.globalapi_ban_sync import (
    GlobalApiBanSyncError,
    sync_player_bans_from_globalapi,
)
from app.services.player_steam_profile import (
    is_player_steam_profile_sync_due,
    sync_player_steam_profile_if_due,
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

router = APIRouter(prefix="/players", tags=["players"])
CurrentSuperuser = Annotated[User, Depends(get_current_active_superuser)]
logger = logging.getLogger(__name__)


def _parse_steamid64(steamid64: str) -> int:
    try:
        return int(steamid64)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid steamid64") from exc


async def _get_player_or_404(*, session: SessionDep, identifier: str) -> Player:
    player = await player_crud.get_player_by_identifier(
        session=session,
        identifier=identifier,
    )
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return player


async def _resolve_player_identifier_to_steamid64_or_404(
    *, session: SessionDep, identifier: str
) -> int:
    steamid64 = await player_crud.resolve_player_identifier_to_steamid64(
        session=session,
        identifier=identifier,
    )
    if steamid64 is None:
        raise HTTPException(status_code=404, detail="Player not found")
    return steamid64


def _ensure_current_user_owns_player(
    *, current_user: CurrentUser, target_steamid64: int
) -> None:
    if current_user.steamid64 != target_steamid64:
        raise HTTPException(
            status_code=403,
            detail="You cannot modify another player's pinned records",
        )


def _ensure_current_user_owns_social_link(
    *, current_user: CurrentUser, target_steamid64: int
) -> None:
    if current_user.steamid64 != target_steamid64:
        raise HTTPException(
            status_code=403,
            detail="You cannot modify another player's social links",
        )


def _ensure_current_user_can_check_own_ban_status(
    *, current_user: CurrentUser, target_steamid64: int
) -> None:
    if current_user.steamid64 != target_steamid64:
        raise HTTPException(
            status_code=403,
            detail="You cannot check another player's ban status",
        )


def _external_base_url(request: Request) -> str:
    forwarded_proto = request.headers.get("x-forwarded-proto")
    forwarded_host = request.headers.get("x-forwarded-host")
    host = forwarded_host or request.headers.get("host")
    if forwarded_proto and host:
        scheme = forwarded_proto.split(",", 1)[0].strip()
        public_host = host.split(",", 1)[0].strip()
        return f"{scheme}://{public_host}".rstrip("/")
    return str(request.base_url).rstrip("/")


def _settings_return_path() -> str:
    return "/settings"


def _twitch_callback_url(_request: Request) -> str:
    return (
        f"{settings.BACKEND_PUBLIC_URL.rstrip('/')}"
        f"{settings.API_V1_STR}"
        f"{router.prefix}/social-links/verify/twitch/callback"
    )


def _ensure_link_is_twitch_and_unverified(*, link: Any) -> None:
    if link.platform != PlayerSocialPlatform.TWITCH:
        raise HTTPException(
            status_code=422,
            detail="Only Twitch links can be verified with this flow",
        )
    if link.verified:
        raise HTTPException(status_code=409, detail="Social link is already verified")


@router.get("/", response_model=PlayersPublic)
async def read_players(
    session: SessionDep,
    query: Annotated[PlayersListQuery, Query()],
) -> Any:
    """
    Retrieve players.
    """
    players, count = await crud.read_players(
        session=session,
        offset=query.offset,
        limit=query.limit,
        sort_by=query.sort_by,
        sort_order=query.sort_order,
    )
    return PlayersPublic(
        data=await crud.to_player_publics(session=session, players=players),
        count=count,
    )


@router.get("/search", response_model=PlayersPublic)
async def search_players(
    session: SessionDep,
    query: Annotated[PlayerSearchQuery, Query()],
) -> PlayersPublic:
    """
    Search players by identifier, name, alias, and rating-weighted relevance.
    """
    players, count = await crud.search_players(
        session=session,
        q=query.q,
        offset=query.offset,
        limit=query.limit,
    )
    return PlayersPublic(
        data=await crud.to_player_publics(session=session, players=players),
        count=count,
    )


@router.post("/", response_model=PlayersBatchPublic)
async def read_players_batch(*, session: SessionDep, body: PlayersBatchRead) -> Any:
    """
    Retrieve players by steamid64 list.
    """
    steamid64s = [_parse_steamid64(steamid64) for steamid64 in body.steamid64s]
    players = await crud.read_players_batch(session=session, steamid64s=steamid64s)
    website_user_steamid64s = await crud.load_website_user_steamid64s(
        session=session,
        steamid64s=[player.steamid64 for player in players if player is not None],
    )
    data: list[PlayerPublic | None] = [
        (
            crud.to_player_public(
                player=player,
                is_website_user=player.steamid64 in website_user_steamid64s,
            )
            if player
            else None
        )
        for player in players
    ]
    return PlayersBatchPublic(data=data, count=len(data))


@router.post("/{identifier:path}/views", response_model=PlayerProfileViewsPublic)
async def create_player_view(
    identifier: str,
    session: SessionDep,
    current_user: CurrentUser,
) -> PlayerProfileViewsPublic:
    """
    Record an authenticated profile view for the current UTC day.
    """
    player = await _get_player_or_404(session=session, identifier=identifier)
    await crud.create_player_profile_view(
        session=session,
        viewer_steamid64=current_user.steamid64,
        target_steamid64=player.steamid64,
    )
    profile_views = await crud.count_player_profile_views(
        session=session,
        target_steamid64=player.steamid64,
    )
    return PlayerProfileViewsPublic(profile_views=profile_views)


@router.get(
    "/{identifier:path}/pinned-records",
    response_model=PlayerPinnedRecordsPublic,
)
async def read_player_pinned_records(
    identifier: str,
    session: SessionDep,
    scope: ModeScope = ModeScope.OVR,
) -> PlayerPinnedRecordsPublic:
    player = await _get_player_or_404(session=session, identifier=identifier)
    pinned_records = await crud.resolve_player_pinned_records_public(
        session=session,
        player_steamid64=player.steamid64,
        scope=scope,
    )
    return PlayerPinnedRecordsPublic(data=pinned_records, count=len(pinned_records))


@router.get(
    "/{identifier:path}/stats",
    response_model=PlayerStatsPublic,
    response_model_exclude_none=True,
)
async def read_player_stats(
    identifier: str,
    session: SessionDep,
    type: Annotated[PlayerStatType | None, Query()] = None,
) -> PlayerStatsPublic:
    player = await _get_player_or_404(session=session, identifier=identifier)
    return await crud.get_or_rebuild_player_stats(
        session=session,
        steamid64=player.steamid64,
        stat_type=type,
    )


@router.get(
    "/{identifier:path}/social-links",
    response_model=PlayerSocialLinksPublic,
)
async def read_player_social_links(
    identifier: str,
    session: SessionDep,
) -> PlayerSocialLinksPublic:
    player = await _get_player_or_404(session=session, identifier=identifier)
    links = await crud.list_player_social_links(
        session=session,
        player_steamid64=player.steamid64,
    )
    return PlayerSocialLinksPublic(
        data=crud.to_player_social_link_publics(links=links),
        count=len(links),
    )


@router.post(
    "/{identifier:path}/social-links",
    response_model=PlayerSocialLinksPublic,
)
async def create_player_social_link(
    identifier: str,
    body: PlayerSocialLinkCreate,
    session: SessionDep,
    current_user: CurrentUser,
) -> PlayerSocialLinksPublic:
    player = await _get_player_or_404(session=session, identifier=identifier)
    _ensure_current_user_owns_social_link(
        current_user=current_user,
        target_steamid64=player.steamid64,
    )

    try:
        await crud.create_player_social_link(
            session=session,
            player_steamid64=player.steamid64,
            url=body.url,
            verified=False,
        )
    except crud.PlayerSocialLinkConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    links = await crud.list_player_social_links(
        session=session,
        player_steamid64=player.steamid64,
    )
    return PlayerSocialLinksPublic(
        data=crud.to_player_social_link_publics(links=links),
        count=len(links),
    )


@router.patch(
    "/{identifier:path}/social-links/{link_id}",
    response_model=PlayerSocialLinksPublic,
)
async def update_player_social_link(
    identifier: str,
    link_id: uuid.UUID,
    body: PlayerSocialLinkUpdate,
    session: SessionDep,
    current_user: CurrentUser,
) -> PlayerSocialLinksPublic:
    player = await _get_player_or_404(session=session, identifier=identifier)
    _ensure_current_user_owns_social_link(
        current_user=current_user,
        target_steamid64=player.steamid64,
    )
    link = await crud.get_player_social_link(session=session, id=link_id)
    if link is None or link.player_steamid64 != player.steamid64:
        raise HTTPException(status_code=404, detail="Social link not found")

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
        player_steamid64=player.steamid64,
    )
    return PlayerSocialLinksPublic(
        data=crud.to_player_social_link_publics(links=links),
        count=len(links),
    )


@router.delete(
    "/{identifier:path}/social-links/{link_id}",
    response_model=PlayerSocialLinksPublic,
)
async def delete_player_social_link(
    identifier: str,
    link_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> PlayerSocialLinksPublic:
    player = await _get_player_or_404(session=session, identifier=identifier)
    _ensure_current_user_owns_social_link(
        current_user=current_user,
        target_steamid64=player.steamid64,
    )
    link = await crud.get_player_social_link(session=session, id=link_id)
    if link is None or link.player_steamid64 != player.steamid64:
        raise HTTPException(status_code=404, detail="Social link not found")

    await crud.delete_player_social_link(session=session, link=link)
    links = await crud.list_player_social_links(
        session=session,
        player_steamid64=player.steamid64,
    )
    return PlayerSocialLinksPublic(
        data=crud.to_player_social_link_publics(links=links),
        count=len(links),
    )


@router.post(
    "/{identifier:path}/social-links/{link_id}/verify/twitch/start",
)
async def start_player_twitch_social_link_verification(
    identifier: str,
    link_id: uuid.UUID,
    request: Request,
    session: SessionDep,
    current_user: CurrentUser,
) -> dict[str, str]:
    player = await _get_player_or_404(session=session, identifier=identifier)
    _ensure_current_user_owns_social_link(
        current_user=current_user,
        target_steamid64=player.steamid64,
    )
    link = await crud.get_player_social_link(session=session, id=link_id)
    if link is None or link.player_steamid64 != player.steamid64:
        raise HTTPException(status_code=404, detail="Social link not found")
    _ensure_link_is_twitch_and_unverified(link=link)

    try:
        ensure_twitch_verification_configured()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    state = create_twitch_verification_state_token(
        steamid64=player.steamid64,
        link_id=str(link.id),
        return_path=_settings_return_path(),
    )
    authorization_url = build_twitch_authorization_url(
        redirect_uri=_twitch_callback_url(request),
        state=state,
    )
    return {"authorization_url": authorization_url}


@router.get("/social-links/verify/twitch/callback")
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
                return_path=_settings_return_path(),
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
            redirect_uri=_twitch_callback_url(request),
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

    try:
        link_id = uuid.UUID(decoded_state.link_id)
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
        _ensure_link_is_twitch_and_unverified(link=link)
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
    "/{identifier:path}/social-links/{link_id}/verify/twitch/confirm",
    response_model=PlayerSocialLinksPublic,
)
async def confirm_player_twitch_social_link_verification(
    identifier: str,
    link_id: uuid.UUID,
    body: PlayerSocialLinkVerifyConfirm,
    session: SessionDep,
    current_user: CurrentUser,
) -> PlayerSocialLinksPublic:
    player = await _get_player_or_404(session=session, identifier=identifier)
    _ensure_current_user_owns_social_link(
        current_user=current_user,
        target_steamid64=player.steamid64,
    )
    link = await crud.get_player_social_link(session=session, id=link_id)
    if link is None or link.player_steamid64 != player.steamid64:
        raise HTTPException(status_code=404, detail="Social link not found")
    _ensure_link_is_twitch_and_unverified(link=link)

    try:
        pending = decode_twitch_pending_confirmation_token(body.pending_token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if (
        pending.steamid64 != player.steamid64
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
        player_steamid64=player.steamid64,
    )
    return PlayerSocialLinksPublic(
        data=crud.to_player_social_link_publics(links=links),
        count=len(links),
    )


@router.post(
    "/{identifier:path}/pinned-records",
    response_model=PlayerPinnedRecordsPublic,
)
async def create_player_pinned_record(
    identifier: str,
    body: PlayerPinnedRecordUpsert,
    session: SessionDep,
    current_user: CurrentUser,
) -> PlayerPinnedRecordsPublic:
    player = await _get_player_or_404(session=session, identifier=identifier)
    _ensure_current_user_owns_player(
        current_user=current_user,
        target_steamid64=player.steamid64,
    )

    records = await crud.get_pb_records(
        session,
        map_id=body.map_id,
        stage=0,
        steamid64=player.steamid64,
        scope=body.scope,
        record_type=body.type,
    )
    if len(records) == 0:
        raise HTTPException(status_code=404, detail="Pinned record target not found")

    await crud.create_player_pinned_record(
        session=session,
        player_steamid64=player.steamid64,
        map_id=body.map_id,
        scope=body.scope,
        record_type=body.type,
    )
    pinned_records = await crud.resolve_player_pinned_records_public(
        session=session,
        player_steamid64=player.steamid64,
        scope=body.scope,
    )
    return PlayerPinnedRecordsPublic(data=pinned_records, count=len(pinned_records))


@router.delete(
    "/{identifier:path}/pinned-records",
    response_model=PlayerPinnedRecordsPublic,
)
async def delete_player_pinned_record(
    identifier: str,
    session: SessionDep,
    current_user: CurrentUser,
    map_id: int,
    scope: ModeScope = ModeScope.OVR,
    type: RecordType = RecordType.NUB,
) -> PlayerPinnedRecordsPublic:
    player = await _get_player_or_404(session=session, identifier=identifier)
    _ensure_current_user_owns_player(
        current_user=current_user,
        target_steamid64=player.steamid64,
    )

    deleted = await crud.delete_player_pinned_record(
        session=session,
        player_steamid64=player.steamid64,
        map_id=map_id,
        scope=scope,
        record_type=type,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Pinned record not found")

    pinned_records = await crud.resolve_player_pinned_records_public(
        session=session,
        player_steamid64=player.steamid64,
        scope=scope,
    )
    return PlayerPinnedRecordsPublic(data=pinned_records, count=len(pinned_records))


@router.get(
    "/{identifier:path}/follow-summary", response_model=PlayerFollowSummaryPublic
)
async def read_player_follow_summary(
    identifier: str,
    session: SessionDep,
    current_user: OptionalCurrentUser,
) -> PlayerFollowSummaryPublic:
    """
    Retrieve follow counts and viewer relationship state for a player.
    """
    player = await _get_player_or_404(session=session, identifier=identifier)
    return await crud.get_player_follow_summary(
        session=session,
        target_steamid64=player.steamid64,
        viewer_steamid64=current_user.steamid64 if current_user else None,
    )


@router.post("/{identifier:path}/follow", response_model=PlayerFollowSummaryPublic)
async def follow_player(
    identifier: str,
    session: SessionDep,
    current_user: CurrentUser,
) -> PlayerFollowSummaryPublic:
    """
    Follow a player.
    """
    player = await _get_player_or_404(session=session, identifier=identifier)
    if current_user.steamid64 == player.steamid64:
        raise HTTPException(status_code=400, detail="You cannot follow yourself")

    await crud.create_player_follow(
        session=session,
        follower_steamid64=current_user.steamid64,
        followed_steamid64=player.steamid64,
    )
    return await crud.get_player_follow_summary(
        session=session,
        target_steamid64=player.steamid64,
        viewer_steamid64=current_user.steamid64,
    )


@router.delete("/{identifier:path}/follow", response_model=PlayerFollowSummaryPublic)
async def unfollow_player(
    identifier: str,
    session: SessionDep,
    current_user: CurrentUser,
) -> PlayerFollowSummaryPublic:
    """
    Unfollow a player.
    """
    player = await _get_player_or_404(session=session, identifier=identifier)
    if current_user.steamid64 == player.steamid64:
        raise HTTPException(status_code=400, detail="You cannot unfollow yourself")

    await crud.delete_player_follow(
        session=session,
        follower_steamid64=current_user.steamid64,
        followed_steamid64=player.steamid64,
    )
    return await crud.get_player_follow_summary(
        session=session,
        target_steamid64=player.steamid64,
        viewer_steamid64=current_user.steamid64,
    )


@router.post(
    "/{identifier:path}/unban-check",
    response_model=PlayerBanStatusCheckPublic,
)
async def check_player_ban_status(
    identifier: str,
    session: SessionDep,
    current_user: CurrentUser,
) -> PlayerBanStatusCheckPublic:
    player = await _get_player_or_404(session=session, identifier=identifier)
    _ensure_current_user_can_check_own_ban_status(
        current_user=current_user,
        target_steamid64=player.steamid64,
    )

    try:
        result = await sync_player_bans_from_globalapi(
            session=session,
            steamid64=player.steamid64,
        )
    except GlobalApiBanSyncError as exc:
        logger.warning(
            "GlobalAPI ban status check failed for steamid64=%s: %s",
            player.steamid64,
            exc,
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if result.remaining_active_ban_count == 0:
        message = (
            "Your ban status has been updated and no active bans remain."
            if result.cleared_active_ban_count > 0
            else "No active bans remain on your profile."
        )
    elif result.cleared_active_ban_count > 0:
        message = "Your ban status has been updated, but active bans still remain."
    else:
        message = "GlobalAPI still reports active bans for your profile."

    return PlayerBanStatusCheckPublic(
        message=message,
        cleared_ban_count=result.cleared_active_ban_count,
        remaining_active_ban_count=result.remaining_active_ban_count,
    )


@router.get(
    "/{identifier:path}/followers",
    dependencies=[Depends(get_current_user)],
    response_model=PlayersPublic,
)
async def read_player_followers(
    identifier: str,
    session: SessionDep,
    query: Annotated[PlayerFollowListQuery, Query()],
) -> PlayersPublic:
    """
    Retrieve followers for a player.
    """
    player = await _get_player_or_404(session=session, identifier=identifier)
    followers, count = await crud.get_player_followers(
        session=session,
        target_steamid64=player.steamid64,
        offset=query.offset,
        limit=query.limit,
    )
    return PlayersPublic(
        data=await crud.to_player_publics(session=session, players=followers),
        count=count,
    )


@router.get(
    "/{identifier:path}/following",
    dependencies=[Depends(get_current_user)],
    response_model=PlayersPublic,
)
async def read_player_following(
    identifier: str,
    session: SessionDep,
    query: Annotated[PlayerFollowListQuery, Query()],
) -> PlayersPublic:
    """
    Retrieve players followed by a player.
    """
    player = await _get_player_or_404(session=session, identifier=identifier)
    following, count = await crud.get_player_following(
        session=session,
        target_steamid64=player.steamid64,
        offset=query.offset,
        limit=query.limit,
    )
    return PlayersPublic(
        data=await crud.to_player_publics(session=session, players=following),
        count=count,
    )


@router.get("/me/settings", response_model=PlayerSettingsPublic)
async def read_current_player_settings(
    session: SessionDep,
    current_user: CurrentUser,
) -> PlayerSettingsPublic:
    player = await crud.get_player_by_steamid64(
        session=session,
        steamid64=current_user.steamid64,
    )
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found")
    return await crud.get_player_settings(session=session, player=player)


@router.patch("/me/settings", response_model=PlayerSettingsPublic)
async def update_current_player_settings(
    session: SessionDep,
    current_user: CurrentUser,
    body: PlayerSettingsUpdate,
) -> PlayerSettingsPublic:
    player = await crud.get_player_by_steamid64(
        session=session,
        steamid64=current_user.steamid64,
    )
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found")

    try:
        return await crud.update_player_settings(
            session=session,
            player=player,
            settings_in=body,
        )
    except crud.PlayerSettingsConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{identifier:path}", response_model=PlayerPublic)
async def read_player(
    identifier: str,
    session: SessionDep,
    background_tasks: BackgroundTasks,
) -> Any:
    """
    Retrieve a player by app custom_id, steamid64, or full Steam profile URL.
    """
    player = await _get_player_or_404(session=session, identifier=identifier)
    if is_player_steam_profile_sync_due(player=player, now=datetime.now(UTC)):
        background_tasks.add_task(
            sync_player_steam_profile_if_due,
            steamid64=player.steamid64,
        )
    return await crud.to_player_public_with_profile_views(session=session, player=player)


@router.put(
    "/{identifier:path}/steam",
    dependencies=[Depends(get_current_user)],
    response_model=PlayerPublic,
)
async def upsert_player_from_steam(session: SessionDep, identifier: str) -> Any:
    """
    Create or update player from a Steam-resolvable identifier.
    """
    parsed_steamid64 = await _resolve_player_identifier_to_steamid64_or_404(
        session=session,
        identifier=identifier,
    )
    player, _ = await crud.create_or_update_player_from_steam_if_fetched(
        session=session,
        steamid64=parsed_steamid64,
    )
    if player is None:
        existing_player = await crud.get_player_by_steamid64(
            session=session,
            steamid64=parsed_steamid64,
        )
        if existing_player is not None:
            return crud.to_player_public(player=existing_player)
        raise HTTPException(status_code=502, detail="Steam profile fetch failed")
    return crud.to_player_public(player=player)


@router.put(
    "/{identifier:path}",
    dependencies=[Depends(get_current_active_superuser)],
    response_model=PlayerPublic,
)
async def update_player(
    *,
    session: SessionDep,
    identifier: str,
    player_in: PlayerUpdate,
    current_user: CurrentSuperuser,
) -> Any:
    """
    Update player profile data.
    """
    del current_user
    db_player = await crud.get_player_by_steamid64(
        session=session,
        steamid64=await _resolve_player_identifier_to_steamid64_or_404(
            session=session,
            identifier=identifier,
        ),
    )
    if not db_player:
        raise HTTPException(status_code=404, detail="Player not found")

    updated_player = await crud.update_player(
        session=session,
        db_player=db_player,
        player_in=player_in,
    )
    return crud.to_player_public(player=updated_player)
