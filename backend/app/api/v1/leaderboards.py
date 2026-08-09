from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app import crud
from app.api.deps import OptionalCurrentUser, SessionDep, get_current_active_superuser
from app.core.regions import is_valid_region_code
from app.crud import player as player_crud
from app.models import (
    CommunityLeaderboardListQuery,
    CommunityLeaderboardsPublic,
    CountryLeaderboardListQuery,
    CountryLeaderboardsPublic,
    JumpstatLeaderboardListQuery,
    JumpstatLeaderboardsPublic,
    MapLeaderboardsPublic,
    Message,
    ModeScope,
    PlayerLeaderboardListQuery,
    PlayerLeaderboardRankPublic,
    PlayerLeaderboardsPublic,
    mode_scope_to_id,
)

router = APIRouter(prefix="/leaderboards", tags=["leaderboards"])


def _validate_geography_filters(
    *,
    country: str | None,
    region: str | None,
    friends_only: bool = False,
) -> None:
    if friends_only and (country is not None or region is not None):
        raise HTTPException(
            status_code=422,
            detail="friends_only cannot be combined with country or region filters.",
        )
    if country is not None and region is not None:
        raise HTTPException(
            status_code=422,
            detail="country and region filters are mutually exclusive. Please provide only one.",
        )
    if region is not None and not is_valid_region_code(region):
        raise HTTPException(status_code=422, detail="Invalid region")


async def _get_player_or_404(*, session: SessionDep, identifier: str):
    player = await player_crud.get_player_by_identifier(
        session=session,
        identifier=identifier,
    )
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found")
    return player


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


@router.get("/jumpstats", response_model=JumpstatLeaderboardsPublic)
async def read_jumpstat_leaderboard(
    session: SessionDep,
    query: Annotated[JumpstatLeaderboardListQuery, Query()],
) -> JumpstatLeaderboardsPublic:
    return await crud.read_jumpstat_leaderboard(session=session, query=query)


@router.get("/community", response_model=CommunityLeaderboardsPublic)
async def read_community_leaderboard(
    session: SessionDep,
    query: Annotated[CommunityLeaderboardListQuery, Query()],
) -> CommunityLeaderboardsPublic:
    data, count = await crud.read_community_leaderboard(
        session=session,
        query=query,
    )
    return CommunityLeaderboardsPublic(data=data, count=count)


@router.get("/countries", response_model=CountryLeaderboardsPublic)
async def read_country_leaderboard(
    session: SessionDep,
    query: Annotated[CountryLeaderboardListQuery, Query()],
) -> CountryLeaderboardsPublic:
    return await crud.read_country_leaderboard(session=session, query=query)


@router.get("/players", response_model=PlayerLeaderboardsPublic)
async def read_player_leaderboard(
    session: SessionDep,
    query: Annotated[PlayerLeaderboardListQuery, Query()],
    current_user: OptionalCurrentUser,
) -> PlayerLeaderboardsPublic:
    _validate_geography_filters(
        country=query.country,
        region=query.region,
        friends_only=query.friends_only,
    )
    data, count = await crud.read_player_leaderboard(
        session=session,
        query=query,
        friends_viewer_steamid64=_get_friends_only_viewer_steamid64(
            friends_only=query.friends_only,
            current_user=current_user,
        ),
    )
    return PlayerLeaderboardsPublic(data=data, count=count)


@router.get("/players/{identifier:path}", response_model=PlayerLeaderboardRankPublic)
async def read_player_leaderboard_rank(
    identifier: str,
    session: SessionDep,
    current_user: OptionalCurrentUser,
    scope: ModeScope = Query(default=ModeScope.OVR),
    country: Annotated[str | None, Query(max_length=2)] = None,
    region: Annotated[str | None, Query(max_length=3)] = None,
    friends_only: bool = Query(default=False),
) -> PlayerLeaderboardRankPublic:
    _validate_geography_filters(
        country=country,
        region=region,
        friends_only=friends_only,
    )
    player = await _get_player_or_404(session=session, identifier=identifier)
    return await crud.read_player_leaderboard_rank(
        session=session,
        player=player,
        scope=scope,
        country=country.strip().upper() if country is not None and country.strip() else None,
        region=region.strip().upper() if region is not None and region.strip() else None,
        friends_viewer_steamid64=_get_friends_only_viewer_steamid64(
            friends_only=friends_only,
            current_user=current_user,
        ),
    )


@router.get("/maps", response_model=MapLeaderboardsPublic)
async def read_map_leaderboard(
    session: SessionDep,
    scope: ModeScope = Query(default=ModeScope.OVR),
) -> MapLeaderboardsPublic:
    return await crud.read_map_leaderboard(session=session, scope=scope)


@router.put(
    "/maps",
    response_model=Message,
    dependencies=[Depends(get_current_active_superuser)],
)
async def upsert_map_leaderboards(
    session: SessionDep,
    scope: ModeScope | None = Query(default=None),
    map_id: int | None = Query(default=None),
) -> Message:
    await crud.rebuild_map_leaderboards(
        session=session,
        scopes=[scope] if scope is not None else None,
        map_ids=[map_id] if map_id is not None else None,
    )
    await session.commit()
    return Message(message="Map leaderboard rows rebuilt successfully")


@router.put("/players/{identifier:path}", response_model=Message)
async def upsert_player_leaderboards(
    identifier: str,
    session: SessionDep,
) -> Message:
    player = await _get_player_or_404(session=session, identifier=identifier)
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found")

    await crud.rebuild_leaderboard_players(
        session=session,
        scope_ids=[mode_scope_to_id(scope) for scope in ModeScope],
        steamid64s=[player.steamid64],
    )
    await session.commit()
    return Message(message="Player leaderboard rows rebuilt successfully")
