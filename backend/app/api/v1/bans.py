from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query

from app import crud
from app.api.deps import SessionDep
from app.models import BanListQuery, BanPublic, BansPublic

router = APIRouter(prefix="/bans", tags=["bans"])


@router.get("", response_model=BansPublic)
async def read_bans(
    session: SessionDep,
    query: Annotated[BanListQuery, Query()],
) -> Any:
    bans, count = await crud.read_bans(session=session, query=query)
    return BansPublic(
        data=[crud.to_ban_public(ban=ban) for ban in bans],
        count=count,
    )


@router.get("/{id:int}", response_model=BanPublic)
async def read_ban(
    session: SessionDep,
    id: int,
) -> BanPublic:
    ban = await crud.get_ban_by_id(session=session, ban_id=id)
    if ban is None:
        raise HTTPException(status_code=404, detail="Ban not found")
    return crud.to_ban_public(ban=ban)
