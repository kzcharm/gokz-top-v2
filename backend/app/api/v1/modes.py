from typing import Any

from fastapi import APIRouter, HTTPException

from app import crud
from app.api.deps import SessionDep
from app.models import ModePublic

router = APIRouter(prefix="/modes", tags=["modes"])


@router.get("/", response_model=list[ModePublic])
async def read_modes(session: SessionDep) -> Any:
    """
    Retrieve all modes.
    """
    modes = await crud.read_modes(session=session)
    return [crud.to_mode_public(mode=mode) for mode in modes]


@router.get("/name/{mode_name}", response_model=ModePublic)
async def read_mode_by_name(session: SessionDep, mode_name: str) -> Any:
    """
    Retrieve a mode by name.
    """
    mode = await crud.get_mode_by_name(session=session, mode_name=mode_name)
    if not mode:
        raise HTTPException(status_code=404, detail="Mode not found")
    return crud.to_mode_public(mode=mode)


@router.get("/id/{id}", response_model=ModePublic)
async def read_mode_by_id(session: SessionDep, id: int) -> Any:
    """
    Retrieve a mode by id.
    """
    mode = await crud.get_mode_by_id(session=session, id=id)
    if not mode:
        raise HTTPException(status_code=404, detail="Mode not found")
    return crud.to_mode_public(mode=mode)
