from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from app import crud
from app.api.deps import SessionDep, get_current_active_superuser
from app.models import ModeAdminUpdate, ModePublic, User

router = APIRouter(prefix="/admin/modes", tags=["admin-modes"])

CurrentSuperuser = Annotated[User, Depends(get_current_active_superuser)]


@router.put("/{id}", response_model=ModePublic)
async def update_mode(
    *,
    session: SessionDep,
    id: int,
    mode_in: ModeAdminUpdate,
    current_user: CurrentSuperuser,
) -> Any:
    """
    Update mode metadata.
    """
    mode = await crud.get_mode_by_id(session=session, id=id)
    if not mode:
        raise HTTPException(status_code=404, detail="Mode not found")

    try:
        mode = await crud.update_mode_metadata(
            session=session,
            db_mode=mode,
            mode_in=mode_in,
            updated_by_id=current_user.steamid64,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid steamid64") from exc

    return crud.to_mode_public(mode=mode)
