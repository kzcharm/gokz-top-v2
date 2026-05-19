from fastapi import APIRouter, HTTPException

from app import crud
from app.api.deps import CurrentUser, SessionDep, user_has_role
from app.models import PlayerSettingsPublic, PlayerSettingsUpdate, UserRole

router = APIRouter(prefix="/me", tags=["me"])


@router.get("/settings", response_model=PlayerSettingsPublic)
async def read_current_player_settings(
    session: SessionDep,
    current_user: CurrentUser,
) -> PlayerSettingsPublic:
    player = await crud.get_player_by_steamid64(
        session=session,
        steamid64=current_user.steamid64,
    )
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found")
    return await crud.get_player_settings(
        session=session,
        player=player,
        bypass_rate_limits=user_has_role(current_user, UserRole.SUPERUSER),
    )


@router.patch("/settings", response_model=PlayerSettingsPublic)
async def update_current_player_settings(
    session: SessionDep,
    current_user: CurrentUser,
    body: PlayerSettingsUpdate,
) -> PlayerSettingsPublic:
    player = await crud.get_player_by_steamid64(
        session=session,
        steamid64=current_user.steamid64,
    )
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found")

    try:
        return await crud.update_player_settings(
            session=session,
            player=player,
            settings_in=body,
            bypass_rate_limits=user_has_role(current_user, UserRole.SUPERUSER),
        )
    except crud.PlayerSettingsConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
