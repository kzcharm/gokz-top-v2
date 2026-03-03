from datetime import timedelta
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app import crud
from app.api.deps import SessionDep
from app.core import security
from app.core.config import settings
from app.models import Token

router = APIRouter(tags=["private"], prefix="/private")


class PrivateAuthSessionCreate(BaseModel):
    steamid64: int
    is_superuser: bool = False
    is_active: bool = True
    name: str | None = None


@router.post("/auth/session", response_model=Token)
async def create_auth_session(
    body: PrivateAuthSessionCreate, session: SessionDep
) -> Any:
    """
    Create or update a user by Steam ID and return a JWT token.
    Development/testing helper endpoint (local env only).
    """
    user = await crud.get_or_create_user_from_steam(
        session=session,
        steamid64=body.steamid64,
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
