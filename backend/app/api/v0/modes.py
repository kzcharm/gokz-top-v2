from typing import Any

from fastapi import APIRouter, HTTPException

from app import crud
from app.api.deps import SessionDep
from app.models import ModeCompatPublicV0

router = APIRouter(prefix="/modes", tags=["modes"])


@router.get("", response_model=list[ModeCompatPublicV0])
async def read_modes(session: SessionDep) -> Any:
    modes = await crud.read_modes(session=session)
    return [crud.to_mode_compat_public_v0(mode=mode) for mode in modes]


@router.get("/name/{mode_name}", response_model=ModeCompatPublicV0)
async def read_mode_by_name(session: SessionDep, mode_name: str) -> Any:
    mode = await crud.get_mode_by_name(session=session, mode_name=mode_name)
    if not mode:
        raise HTTPException(status_code=404, detail="Mode not found")
    return crud.to_mode_compat_public_v0(mode=mode)


@router.get("/id/{id}", response_model=ModeCompatPublicV0)
async def read_mode_by_id(session: SessionDep, id: int) -> Any:
    mode = await crud.get_mode_by_id(session=session, id=id)
    if not mode:
        raise HTTPException(status_code=404, detail="Mode not found")
    return crud.to_mode_compat_public_v0(mode=mode)
