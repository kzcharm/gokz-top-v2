from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app import crud
from app.api.deps import SessionDep, get_current_user
from app.crud import player as player_crud
from app.models import (
    PlayerPublic,
    PlayersBatchPublic,
    PlayersBatchRead,
    PlayersListQuery,
    PlayersPublic,
    PlayerUpdate,
)

router = APIRouter(prefix="/players", tags=["players"])


def _parse_steamid64(steamid64: str) -> int:
    try:
        return int(steamid64)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid steamid64") from exc


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
        data=[crud.to_player_public(player=player) for player in players],
        count=count,
    )


@router.post("/", response_model=PlayersBatchPublic)
async def read_players_batch(*, session: SessionDep, body: PlayersBatchRead) -> Any:
    """
    Retrieve players by steamid64 list.
    """
    steamid64s = [_parse_steamid64(steamid64) for steamid64 in body.steamid64s]
    players = await crud.read_players_batch(session=session, steamid64s=steamid64s)

    data: list[PlayerPublic | None] = [
        crud.to_player_public(player=player) if player else None for player in players
    ]
    return PlayersBatchPublic(data=data, count=len(data))


@router.get("/{identifier}", response_model=PlayerPublic)
async def read_player(identifier: str, session: SessionDep) -> Any:
    """
    Retrieve a player by steamid64 or custom_id.
    """
    player = await player_crud.get_player_by_identifier(
        session=session, identifier=identifier
    )
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return crud.to_player_public(player=player)


@router.put(
    "/{steamid64}/steam",
    dependencies=[Depends(get_current_user)],
    response_model=PlayerPublic,
)
async def upsert_player_from_steam(session: SessionDep, steamid64: str) -> Any:
    """
    Create or update player from Steam API.
    """
    player = await crud.create_or_update_player_from_steam(
        session=session,
        steamid64=_parse_steamid64(steamid64),
    )
    return crud.to_player_public(player=player)


@router.put(
    "/{steamid64}",
    dependencies=[Depends(get_current_user)],
    response_model=PlayerPublic,
)
async def update_player(
    *,
    session: SessionDep,
    steamid64: str,
    player_in: PlayerUpdate,
) -> Any:
    """
    Update player profile data.
    """
    db_player = await crud.get_player_by_steamid64(
        session=session,
        steamid64=_parse_steamid64(steamid64),
    )
    if not db_player:
        raise HTTPException(status_code=404, detail="Player not found")

    updated_player = await crud.update_player(
        session=session,
        db_player=db_player,
        player_in=player_in,
    )
    return crud.to_player_public(player=updated_player)
