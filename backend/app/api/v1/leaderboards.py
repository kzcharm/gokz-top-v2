from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app import crud
from app.api.deps import SessionDep
from app.models import (
    Message,
    PlayerLeaderboardListQuery,
    PlayerLeaderboardsPublic,
    RecordScope,
    scope_to_id,
)

router = APIRouter(prefix="/leaderboards", tags=["leaderboards"])


def _parse_steamid64(steamid64: str) -> int:
    try:
        return int(steamid64)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid steamid64") from exc


@router.get("/players", response_model=PlayerLeaderboardsPublic)
async def read_player_leaderboard(
    session: SessionDep,
    query: Annotated[PlayerLeaderboardListQuery, Query()],
) -> PlayerLeaderboardsPublic:
    data, count = await crud.read_player_leaderboard(session=session, query=query)
    return PlayerLeaderboardsPublic(data=data, count=count)


@router.put("/players/{steamid64}", response_model=Message)
async def upsert_player_leaderboards(
    steamid64: str,
    session: SessionDep,
) -> Message:
    player_steamid64 = _parse_steamid64(steamid64)
    player = await crud.get_player_by_steamid64(
        session=session,
        steamid64=player_steamid64,
    )
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found")

    await crud.rebuild_leaderboard_players(
        session=session,
        scope_ids=[scope_to_id(scope) for scope in RecordScope],
        steamid64s=[player_steamid64],
    )
    await session.commit()
    return Message(message="Player leaderboard rows rebuilt successfully")
