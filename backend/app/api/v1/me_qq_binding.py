from fastapi import APIRouter, HTTPException

from app.api.deps import CurrentUser
from app.models import QQBindingCodePublic
from app.services.qq_binding import create_qq_binding_code

router = APIRouter(prefix="/me", tags=["me"])


@router.post("/qq-binding-code", response_model=QQBindingCodePublic)
async def create_current_player_qq_binding_code(
    current_user: CurrentUser,
) -> QQBindingCodePublic:
    try:
        return create_qq_binding_code(steamid64=current_user.steamid64)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
