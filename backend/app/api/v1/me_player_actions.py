from datetime import UTC, datetime
from math import ceil

from fastapi import APIRouter, HTTPException, Path

from app import crud
from app.api.deps import CurrentUser, SessionDep
from app.api.v1.player_api_helpers import (
    ensure_current_user_can_check_own_ban_status,
    ensure_current_user_owns_player,
    get_player_or_404,
    logger,
)
from app.models import (
    ModeScope,
    PlayerBanStatusCheckPublic,
    PlayerFriendsPublic,
    PlayerPinnedRecordsPublic,
    PlayerPinnedRecordUpsert,
    RecordType,
)
from app.services.globalapi_ban_sync import (
    GlobalApiBanSyncError,
    sync_player_bans_from_globalapi,
)
from app.services.player_friends import (
    format_friends_sync_retry_wait,
    read_player_friends_public,
    sync_player_friends,
)

router = APIRouter(prefix="/me", tags=["me"])


@router.post("/friend-sync-requests", response_model=PlayerFriendsPublic)
async def sync_current_player_friends(
    session: SessionDep,
    current_user: CurrentUser,
) -> PlayerFriendsPublic:
    player = await get_player_or_404(
        session=session,
        identifier=str(current_user.steamid64),
    )
    result = await sync_player_friends(session=session, player=player)
    if result.kind == "rate_limited":
        now = datetime.now(UTC)
        wait = format_friends_sync_retry_wait(
            now=now,
            next_allowed_at=result.next_allowed_at,
        )
        retry_after_seconds = max(
            1,
            ceil((result.next_allowed_at - now).total_seconds())
            if result.next_allowed_at is not None
            else 1,
        )
        raise HTTPException(
            status_code=429,
            detail=f"Friends sync is rate limited. Wait {wait} before retrying.",
            headers={"Retry-After": str(retry_after_seconds)},
        )
    if result.kind == "failed":
        raise HTTPException(status_code=502, detail="Friends sync failed")

    return await read_player_friends_public(session=session, player=player)


@router.post("/ban-status-checks", response_model=PlayerBanStatusCheckPublic)
async def check_current_player_ban_status(
    session: SessionDep,
    current_user: CurrentUser,
) -> PlayerBanStatusCheckPublic:
    player = await get_player_or_404(
        session=session,
        identifier=str(current_user.steamid64),
    )
    ensure_current_user_can_check_own_ban_status(
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


@router.post("/pinned-records", response_model=PlayerPinnedRecordsPublic)
async def create_current_player_pinned_record(
    body: PlayerPinnedRecordUpsert,
    session: SessionDep,
    current_user: CurrentUser,
) -> PlayerPinnedRecordsPublic:
    player = await get_player_or_404(
        session=session,
        identifier=str(current_user.steamid64),
    )
    ensure_current_user_owns_player(
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
    "/pinned-records/{map_id}/{scope}/{type}",
    response_model=PlayerPinnedRecordsPublic,
)
async def delete_current_player_pinned_record(
    session: SessionDep,
    current_user: CurrentUser,
    map_id: int,
    scope: ModeScope,
    type: RecordType = Path(),
) -> PlayerPinnedRecordsPublic:
    player = await get_player_or_404(
        session=session,
        identifier=str(current_user.steamid64),
    )
    ensure_current_user_owns_player(
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
