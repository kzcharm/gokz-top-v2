import logging
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from app import crud
from app.api.deps import (
    CurrentUser,
    OptionalCurrentUser,
    SessionDep,
    get_current_active_superuser,
)
from app.core.regions import is_valid_region_code
from app.models import (
    MapPublic,
    MapPbLeaderboardPublic,
    MapReviewListQuery,
    MapReviewPublic,
    MapReviewsPublic,
    MapReviewUpsert,
    MapSyncResult,
    MapWrPublic,
    ModeScope,
    RecordType,
    ServerGroupStatus,
)
from app.services.globalapi_maps_sync import (
    GlobalAPIMapsSyncError,
    sync_maps_from_globalapi,
)

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
    limit: Annotated[int, Query(ge=1, le=10000)] = 100,
    id: Annotated[list[int] | None, Query()] = None,
    name: Annotated[str | None, Query()] = None,
    larger_than_filesize: Annotated[int | None, Query()] = None,
    smaller_than_filesize: Annotated[int | None, Query()] = None,
    is_validated: Annotated[bool | None, Query()] = None,
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
        created_since=_parse_datetime(created_since),
        updated_since=_parse_datetime(updated_since),
    )
    return await crud.to_map_publics(session=session, maps=maps)


@router.get("/name/{map_name}", response_model=MapPublic)
async def read_map_by_name(
    session: SessionDep,
    map_name: str,
) -> MapPublic:
    map_obj = await crud.get_map_by_name(session=session, map_name=map_name)
    if not map_obj:
        raise HTTPException(status_code=404, detail="Map not found")
    return (await crud.to_map_publics(session=session, maps=[map_obj]))[0]


@router.get("/{id:int}/leaderboard", response_model=MapPbLeaderboardPublic)
async def read_map_pb_leaderboard(
    session: SessionDep,
    id: int,
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
    map_obj = await crud.get_map_by_id(session=session, id=id)
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


@router.get("/{id:int}", response_model=MapPublic)
async def read_map_by_id(
    session: SessionDep,
    id: int,
) -> MapPublic:
    map_obj = await crud.get_map_by_id(session=session, id=id)
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
) -> int:
    if server_group_id is not None:
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
) -> MapReviewPublic:
    if current_user is None and not x_server_group_key:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if current_user is not None and x_server_group_key:
        raise HTTPException(
            status_code=400,
            detail="Use either user auth or a server group API key",
        )

    server_group_id: uuid.UUID | None = None
    if x_server_group_key:
        group = await crud.get_server_group_by_api_key(
            session=session,
            api_key=x_server_group_key,
        )
        if group is None:
            raise HTTPException(status_code=401, detail="Invalid server group API key")
        if group.status == ServerGroupStatus.INVALIDATED:
            raise HTTPException(status_code=403, detail="Server group is invalidated")
        server_group_id = group.id

    steamid64 = _resolve_review_target_steamid64(
        current_user_steamid64=current_user.steamid64 if current_user else None,
        payload_steamid64=payload.steamid64,
        server_group_id=server_group_id,
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
) -> MapReviewPublic:
    map_obj = await crud.get_map_by_id(session=session, id=map_id)
    if map_obj is None:
        raise HTTPException(status_code=404, detail="Map not found")

    cleared_review = await crud.clear_map_review_comments(
        session=session,
        steamid64=current_user.steamid64,
        map_id=map_id,
    )
    if cleared_review is None:
        raise HTTPException(status_code=404, detail="Map review not found")

    await crud.rebuild_map_review_summary(session=session, map_id=map_id)
    review, player, map_obj = cleared_review
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
