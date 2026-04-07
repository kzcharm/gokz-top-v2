from datetime import timedelta
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from app import crud
from app.api.deps import SessionDep
from app.core import security
from app.core.config import settings
from app.models import Token

router = APIRouter(tags=["private"], prefix="/private")


def ensure_test_auth_helpers_enabled() -> None:
    if settings.ENABLE_TEST_AUTH_HELPERS:
        return
    raise HTTPException(status_code=404, detail="Not found")


class PrivateAuthSessionCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "steamid64": str(settings.SUPER_USER_STEAMID64),
                "is_superuser": True,
                "is_active": True,
                "name": "Docs Admin",
            }
        }
    )

    steamid64: str | int = str(settings.SUPER_USER_STEAMID64)
    is_superuser: bool = True
    is_active: bool = True
    name: str | None = "Docs Admin"


@router.post("/auth/session", response_model=Token)
async def create_auth_session(
    body: PrivateAuthSessionCreate, session: SessionDep
) -> Any:
    """
    Create or update a user by Steam ID and return a JWT token.
    Development/testing helper endpoint (local env only).
    """
    ensure_test_auth_helpers_enabled()
    steamid64 = int(body.steamid64)
    user = await crud.get_or_create_user_from_steam(
        session=session,
        steamid64=steamid64,
    )

    if body.name:
        player = await crud.get_player_by_steamid64(
            session=session,
            steamid64=user.steamid64,
        )
        if player:
            player.name = body.name
            session.add(player)

    user.is_superuser = body.is_superuser
    user.is_active = body.is_active
    session.add(user)
    await session.commit()
    await session.refresh(user)

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    token = security.create_access_token(
        user.steamid64, expires_delta=access_token_expires
    )
    return Token(access_token=token, token_type="bearer")
