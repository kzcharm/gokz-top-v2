import logging
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query
from fastapi.responses import RedirectResponse

from app import crud
from app.api.deps import (
    CurrentUser,
    OptionalCurrentUser,
    SessionDep,
    get_current_active_superuser,
    user_has_any_role,
)
from app.core.regions import is_valid_region_code
from app.crud.server import mark_server_group_api_key_used
from app.models import (
    MapFileDistributionSyncResult,
    MapPbLeaderboardPublic,
    MapPublic,
    MapReviewListQuery,
    MapReviewPublic,
    MapReviewsPublic,
    MapReviewUpsert,
    MapStatsPublic,
    MapSyncResult,
    MapWrHistoryPublic,
    MapWrPublic,
    ModeScope,
    RecordType,
    ServerGroupStatus,
    UserRole,
)
from app.services.globalapi_maps_sync import (
    GlobalAPIMapsSyncError,
    sync_maps_from_globalapi,
)
from app.services.map_file_distribution import (
    MapFileDistributionError,
    sync_map_files,
)
from app.services.qq_binding import verify_qq_bot_api_key
from app.services.steam_workshop import fetch_workshop_preview_url

router = APIRouter(prefix="/maps", tags=["maps"])
logger = logging.getLogger(__name__)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.year >= 1900 else None
    except ValueError:
        return None


def _validate_geography_filters(*, country: str | None, region: str | None) -> None:
    if country is not None and region is not None:
        raise HTTPException(
            status_code=422,
            detail="country and region filters are mutually exclusive. Please provide only one.",
        )
    if region is not None and not is_valid_region_code(region):
        raise HTTPException(status_code=422, detail="Invalid region")


def _validate_map_leaderboard_filters(
    *,
    country: str | None,
    region: str | None,
    friends_only: bool,
) -> None:
    if friends_only and (country is not None or region is not None):
        raise HTTPException(
            status_code=422,
            detail="friends_only cannot be combined with country or region filters.",
        )
    _validate_geography_filters(country=country, region=region)


def _get_friends_only_viewer_steamid64(
    *,
    friends_only: bool,
    current_user: OptionalCurrentUser,
) -> int | None:
    if not friends_only:
        return None
    if current_user is None:
        raise HTTPException(
            status_code=403,
            detail="Login is required to view a friends-only leaderboard.",
        )
    return current_user.steamid64


@router.get("", response_model=list[MapPublic])
async def read_maps(
    session: SessionDep,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100000)] = 100,
    id: Annotated[list[int] | None, Query()] = None,
    name: Annotated[str | None, Query()] = None,
    larger_than_filesize: Annotated[int | None, Query()] = None,
    smaller_than_filesize: Annotated[int | None, Query()] = None,
    is_validated: Annotated[bool | None, Query()] = None,
    scope: Annotated[ModeScope | None, Query()] = None,
    created_since: Annotated[str | None, Query()] = None,
    updated_since: Annotated[str | None, Query()] = None,
) -> list[MapPublic]:
    maps = await crud.read_maps_v1(
        session=session,
        offset=offset,
        limit=limit,
        id=id,
        name=name,
        larger_than_filesize=larger_than_filesize,
        smaller_than_filesize=smaller_than_filesize,
        is_validated=is_validated,
        scope=scope,
        created_since=_parse_datetime(created_since),
        updated_since=_parse_datetime(updated_since),
    )
    return await crud.to_map_publics(session=session, maps=maps)


@router.get("/workshop/{workshop_id}/preview-image", response_model=None)
async def read_workshop_preview_image(
    workshop_id: Annotated[str, Path(pattern=r"^\d+$")],
) -> RedirectResponse:
    preview_url = await fetch_workshop_preview_url(workshop_id=workshop_id)
    if preview_url is None:
        raise HTTPException(status_code=404, detail="Workshop preview not found")
    return RedirectResponse(url=preview_url)


@router.get("/{map_id:int}/leaderboard", response_model=MapPbLeaderboardPublic)
async def read_map_pb_leaderboard(
    session: SessionDep,
    map_id: int,
    current_user: OptionalCurrentUser,
    scope: ModeScope = ModeScope.OVR,
    type: RecordType = RecordType.NUB,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    stage: Annotated[int, Query(ge=0)] = 0,
    country: Annotated[str | None, Query(max_length=2)] = None,
    region: Annotated[str | None, Query(max_length=3)] = None,
    friends_only: bool = Query(default=False),
) -> MapPbLeaderboardPublic:
    map_obj = await crud.get_map_by_id(session=session, id=map_id)
    if map_obj is None:
        raise HTTPException(status_code=404, detail="Map not found")

    normalized_country = country.strip().upper() if country is not None and country.strip() else None
    normalized_region = region.strip().upper() if region is not None and region.strip() else None
    _validate_map_leaderboard_filters(
        country=normalized_country,
        region=normalized_region,
        friends_only=friends_only,
    )

    return await crud.read_map_pb_leaderboard(
        session=session,
        map_id=map_obj.id,
        stage=stage,
        scope=scope,
        record_type=type,
        country=normalized_country,
        region=normalized_region,
        offset=offset,
        limit=limit,
        viewer_steamid64=current_user.steamid64 if current_user is not None else None,
        friends_viewer_steamid64=_get_friends_only_viewer_steamid64(
            friends_only=friends_only,
            current_user=current_user,
        ),
    )


@router.get("/wrs", response_model=list[MapWrPublic])
async def read_map_wrs(
    session: SessionDep,
    scope: ModeScope = ModeScope.OVR,
    type: Annotated[RecordType | None, Query()] = None,
    map_id: Annotated[int | None, Query()] = None,
    map_name: Annotated[str | None, Query()] = None,
) -> list[MapWrPublic]:
    if map_id is not None and map_name is not None:
        raise HTTPException(
            status_code=422,
            detail="map_id and map_name filters are mutually exclusive. Please provide only one.",
        )

    resolved_map_id = map_id
    if map_name is not None:
        map_obj = await crud.get_map_by_name(session=session, map_name=map_name)
        if map_obj is None:
            return []
        resolved_map_id = map_obj.id

    return await crud.read_map_wrs(
        session=session,
        map_id=resolved_map_id,
        scope=scope,
        record_type=type,
    )


@router.get("/{map_id:int}/wr-history", response_model=MapWrHistoryPublic)
async def read_map_wr_history(
    session: SessionDep,
    map_id: int,
    scope: ModeScope = ModeScope.OVR,
    type: RecordType = RecordType.NUB,
) -> MapWrHistoryPublic:
    map_obj = await crud.get_map_by_id(session=session, id=map_id)
    if map_obj is None:
        raise HTTPException(status_code=404, detail="Map not found")

    return await crud.read_map_wr_history(
        session=session,
        map_id=map_obj.id,
        scope=scope,
        record_type=type,
    )


@router.get("/{map_id:int}/stats", response_model=MapStatsPublic)
async def read_map_stats(
    session: SessionDep,
    map_id: int,
    scope: ModeScope = ModeScope.OVR,
) -> MapStatsPublic:
    map_obj = await crud.get_map_by_id(session=session, id=map_id)
    if map_obj is None:
        raise HTTPException(status_code=404, detail="Map not found")

    return await crud.get_or_rebuild_map_stats(
        session=session,
        map_id=map_obj.id,
        scope=scope,
    )


@router.get("/{map_id:int}", response_model=MapPublic)
async def read_map_by_id(
    session: SessionDep,
    map_id: int,
) -> MapPublic:
    map_obj = await crud.get_map_by_id(session=session, id=map_id)
    if not map_obj:
        raise HTTPException(status_code=404, detail="Map not found")
    return (await crud.to_map_publics(session=session, maps=[map_obj]))[0]


@router.get("/reviews", response_model=MapReviewsPublic)
async def read_map_reviews(
    session: SessionDep,
    query: Annotated[MapReviewListQuery, Query()],
) -> MapReviewsPublic:
    map_id = query.map_id
    if query.map_name is not None:
        map_obj = await crud.get_map_by_name(session=session, map_name=query.map_name)
        if map_obj is None:
            return MapReviewsPublic(data=[], count=0)
        map_id = map_obj.id

    reviews, count = await crud.read_latest_map_reviews(
        session=session,
        offset=query.offset,
        limit=query.limit,
        map_id=map_id,
        steamid64=query.steamid64,
        with_comments_only=query.with_comments_only,
        language=query.language,
        source=query.source,
    )
    return MapReviewsPublic(
        data=[
            crud.to_map_review_public(review=review, player=player, map_obj=map_obj)
            for review, player, map_obj in reviews
        ],
        count=count,
    )


def _resolve_review_target_steamid64(
    *,
    current_user_steamid64: int | None,
    payload_steamid64: int | None,
    server_group_id: uuid.UUID | None,
    qq_bot_authenticated: bool,
) -> int:
    if server_group_id is not None:
        if payload_steamid64 is None:
            raise HTTPException(status_code=422, detail="steamid64 is required")
        return payload_steamid64
    if qq_bot_authenticated:
        if payload_steamid64 is None:
            raise HTTPException(status_code=422, detail="steamid64 is required")
        return payload_steamid64
    assert current_user_steamid64 is not None
    return current_user_steamid64


@router.put("/reviews", response_model=MapReviewPublic)
async def put_map_review(
    *,
    session: SessionDep,
    payload: MapReviewUpsert,
    current_user: OptionalCurrentUser,
    x_server_group_key: Annotated[
        str | None, Header(alias="X-Server-Group-Key")
    ] = None,
    x_qq_bot_key: Annotated[str | None, Header(alias="X-QQ-Bot-Key")] = None,
) -> MapReviewPublic:
    if current_user is None and not x_server_group_key and not x_qq_bot_key:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if current_user is not None and (x_server_group_key or x_qq_bot_key):
        raise HTTPException(
            status_code=400,
            detail="Use either user auth or a machine API key",
        )
    if x_server_group_key and x_qq_bot_key:
        raise HTTPException(
            status_code=400,
            detail="Use only one machine API key",
        )

    server_group_id: uuid.UUID | None = None
    qq_bot_authenticated = False
    if x_server_group_key:
        group = await crud.get_server_group_by_api_key(
            session=session,
            api_key=x_server_group_key,
        )
        if group is None:
            raise HTTPException(status_code=401, detail="Invalid server group API key")
        if group.status == ServerGroupStatus.INVALIDATED:
            raise HTTPException(status_code=403, detail="Server group is invalidated")
        mark_server_group_api_key_used(session=session, group=group)
        server_group_id = group.id
    elif x_qq_bot_key:
        if not await verify_qq_bot_api_key(session=session, api_key=x_qq_bot_key):
            raise HTTPException(status_code=401, detail="Invalid QQ bot API key")
        qq_bot_authenticated = True

    steamid64 = _resolve_review_target_steamid64(
        current_user_steamid64=current_user.steamid64 if current_user else None,
        payload_steamid64=payload.steamid64,
        server_group_id=server_group_id,
        qq_bot_authenticated=qq_bot_authenticated,
    )
    map_obj = await crud.get_map_by_id(session=session, id=payload.map_id)
    if map_obj is None:
        raise HTTPException(status_code=404, detail="Map not found")
    player = await crud.get_player_by_steamid64(session=session, steamid64=steamid64)
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found")
    if not await crud.has_finished_map_for_review(
        session=session,
        steamid64=steamid64,
        map_id=payload.map_id,
    ):
        raise HTTPException(
            status_code=403,
            detail="Player must have an OVR PB on the map before submitting a review",
        )

    review, player, map_obj = await crud.upsert_map_review(
        session=session,
        steamid64=steamid64,
        map_id=payload.map_id,
        server_group_id=server_group_id,
        content_in=payload.content,
    )
    await crud.rebuild_map_review_summary(session=session, map_id=payload.map_id)
    return crud.to_map_review_public(review=review, player=player, map_obj=map_obj)


@router.delete("/reviews", response_model=MapReviewPublic)
async def delete_map_review_comments(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    map_id: Annotated[int, Query()],
    steamid64: Annotated[str | None, Query()] = None,
) -> MapReviewPublic:
    map_obj = await crud.get_map_by_id(session=session, id=map_id)
    if map_obj is None:
        raise HTTPException(status_code=404, detail="Map not found")

    target_steamid64 = current_user.steamid64
    if steamid64 is not None:
        if not user_has_any_role(current_user, UserRole.SUPERUSER, UserRole.ADMIN):
            raise HTTPException(
                status_code=403,
                detail="The user doesn't have enough privileges",
            )
        try:
            target_steamid64 = int(steamid64)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid steamid64") from None

    cleared_review = await crud.clear_map_review_comments(
        session=session,
        steamid64=target_steamid64,
        map_id=map_id,
    )
    if cleared_review is None:
        raise HTTPException(status_code=404, detail="Map review not found")

    await crud.rebuild_map_review_summary(session=session, map_id=map_id)
    review, player, map_obj, deleted_comment_texts = cleared_review
    if deleted_comment_texts:
        await crud.create_map_review_comment_deleted_notification(
            session=session,
            recipient_steamid64=target_steamid64,
            map_id=map_id,
            map_name=map_obj.name,
            comment_text="\n\n---\n\n".join(deleted_comment_texts),
        )
    return crud.to_map_review_public(review=review, player=player, map_obj=map_obj)


@router.post(
    "/sync",
    response_model=MapSyncResult,
    dependencies=[Depends(get_current_active_superuser)],
)
async def trigger_map_sync(
    session: SessionDep,
) -> MapSyncResult:
    try:
        return await sync_maps_from_globalapi(session=session)
    except GlobalAPIMapsSyncError as exc:
        logger.warning("GlobalAPI map sync failed: %s", exc)
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected map sync failure")
        raise HTTPException(
            status_code=500, detail="Failed to sync maps due to internal error"
        ) from exc


@router.post(
    "/files/sync",
    response_model=MapFileDistributionSyncResult,
    dependencies=[Depends(get_current_active_superuser)],
)
async def trigger_map_file_sync(
    session: SessionDep,
    force: Annotated[bool, Query()] = False,
) -> MapFileDistributionSyncResult:
    try:
        result = await sync_map_files(session=session, force=force)
    except MapFileDistributionError as exc:
        logger.warning("Map file distribution failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if result.disabled:
        raise HTTPException(
            status_code=403,
            detail="Map file distribution is enabled only in production",
        )
    return result
