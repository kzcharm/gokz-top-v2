import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app import crud
from app.api.deps import SessionDep
from app.models import (
    JumpstatDetailPublic,
    JumpstatListQuery,
    JumpstatsPublic,
)

router = APIRouter(prefix="/jumpstats", tags=["jumpstats"])


@router.get("", response_model=JumpstatsPublic)
async def read_jumpstats(
    session: SessionDep,
    query: Annotated[JumpstatListQuery, Query()],
) -> JumpstatsPublic:
    rows, count = await crud.read_jumpstats(session=session, query=query)
    return JumpstatsPublic(data=crud.to_jumpstat_publics(rows=rows), count=count)


@router.get("/{jumpstat_id}", response_model=JumpstatDetailPublic)
async def read_jumpstat(
    session: SessionDep,
    jumpstat_id: uuid.UUID,
) -> JumpstatDetailPublic:
    row = await crud.get_jumpstat_by_id(session=session, jumpstat_id=jumpstat_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Jumpstat not found")

    jumpstat, player, server_group = row
    return crud.to_jumpstat_detail_public(
        jumpstat=jumpstat,
        player=player,
        server_group=server_group,
    )
