from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app import crud
from app.api.deps import SessionDep
from app.models import ModePublic

router = APIRouter(prefix="/modes", tags=["modes"])


@router.get("", response_model=list[ModePublic])
async def read_modes(
    session: SessionDep,
    name: Annotated[str | None, Query()] = None,
) -> list[ModePublic]:
    """
    Retrieve all modes or filter by exact name.
    """
    if name is not None:
        mode = await crud.get_mode_by_name(session=session, mode_name=name)
        if not mode:
            return []
        return [crud.to_mode_public(mode=mode)]
    modes = await crud.read_modes(session=session)
    return [crud.to_mode_public(mode=mode) for mode in modes]


@router.get("/{mode_id}", response_model=ModePublic)
async def read_mode_by_id(session: SessionDep, mode_id: int) -> ModePublic:
    """
    Retrieve a mode by id.
    """
    mode = await crud.get_mode_by_id(session=session, id=mode_id)
    if not mode:
        raise HTTPException(status_code=404, detail="Mode not found")
    return crud.to_mode_public(mode=mode)
