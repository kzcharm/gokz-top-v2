from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app import crud
from app.api.deps import SessionDep
from app.models import BanListQuery, BanPublic, BansPublic

router = APIRouter(prefix="/bans", tags=["bans"])


@router.get("", response_model=BansPublic)
async def read_bans(
    session: SessionDep,
    query: Annotated[BanListQuery, Query()],
) -> BansPublic:
    bans, count = await crud.read_bans(session=session, query=query)
    return BansPublic(
        data=[crud.to_ban_public(ban=ban, player=player) for ban, player in bans],
        count=count,
    )


@router.get("/{id:int}", response_model=BanPublic)
async def read_ban(
    session: SessionDep,
    id: int,
) -> BanPublic:
    ban_with_player = await crud.get_ban_by_id(session=session, ban_id=id)
    if ban_with_player is None:
        raise HTTPException(status_code=404, detail="Ban not found")
    ban, player = ban_with_player
    return crud.to_ban_public(ban=ban, player=player)
