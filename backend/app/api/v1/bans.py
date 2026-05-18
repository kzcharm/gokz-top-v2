import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app import crud
from app.api.deps import SessionDep, get_current_active_superuser
from app.models import BanCreate, BanListQuery, BanPublic, BansPublic, User

router = APIRouter(prefix="/bans", tags=["bans"])

CurrentSuperuser = Annotated[User, Depends(get_current_active_superuser)]


def _parse_steamid64(value: str) -> int:
    normalized = value.strip()
    if not normalized.isdigit():
        raise HTTPException(status_code=422, detail="steamid64 must be numeric")
    return int(normalized)


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


@router.post("", response_model=BanPublic)
async def create_ban(
    *,
    session: SessionDep,
    body: BanCreate,
    current_user: CurrentSuperuser,
) -> BanPublic:
    steamid64 = _parse_steamid64(body.steamid64)
    player = await crud.get_player_by_steamid64(session=session, steamid64=steamid64)
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found")

    ban = await crud.create_manual_ban(
        session=session,
        body=body,
        steamid64=steamid64,
        updated_by_steamid64=current_user.steamid64,
    )
    return crud.to_ban_public(ban=ban, player=player)


@router.get("/{ban_uuid}", response_model=BanPublic)
async def read_ban(
    session: SessionDep,
    ban_uuid: uuid.UUID,
) -> BanPublic:
    ban_with_player = await crud.get_ban_by_uuid(
        session=session,
        ban_uuid=ban_uuid,
    )
    if ban_with_player is None:
        raise HTTPException(status_code=404, detail="Ban not found")
    ban, player = ban_with_player
    return crud.to_ban_public(ban=ban, player=player)
