from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app import crud
from app.api.deps import SessionDep
from app.core.regions import is_valid_region_code
from app.crud import player as player_crud
from app.models import (
    Message,
    PlayerLeaderboardListQuery,
    PlayerLeaderboardRankPublic,
    PlayerLeaderboardsPublic,
    RecordScope,
    scope_to_id,
)

router = APIRouter(prefix="/leaderboards", tags=["leaderboards"])

def _validate_geography_filters(*, country: str | None, region: str | None) -> None:
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


@router.get("/players", response_model=PlayerLeaderboardsPublic)
async def read_player_leaderboard(
    session: SessionDep,
    query: Annotated[PlayerLeaderboardListQuery, Query()],
) -> PlayerLeaderboardsPublic:
    _validate_geography_filters(country=query.country, region=query.region)
    data, count = await crud.read_player_leaderboard(session=session, query=query)
    return PlayerLeaderboardsPublic(data=data, count=count)


@router.get("/players/{identifier:path}", response_model=PlayerLeaderboardRankPublic)
async def read_player_leaderboard_rank(
    identifier: str,
    session: SessionDep,
    scope: RecordScope = Query(default=RecordScope.OVR),
    country: Annotated[str | None, Query(max_length=2)] = None,
    region: Annotated[str | None, Query(max_length=3)] = None,
) -> PlayerLeaderboardRankPublic:
    _validate_geography_filters(country=country, region=region)
    player = await _get_player_or_404(session=session, identifier=identifier)
    return await crud.read_player_leaderboard_rank(
        session=session,
        player=player,
        scope=scope,
        country=country.strip().upper() if country is not None and country.strip() else None,
        region=region.strip().upper() if region is not None and region.strip() else None,
    )


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
        scope_ids=[scope_to_id(scope) for scope in RecordScope],
        steamid64s=[player.steamid64],
    )
    await session.commit()
    return Message(message="Player leaderboard rows rebuilt successfully")
