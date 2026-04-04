from collections.abc import AsyncGenerator
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidTokenError
from pydantic import ValidationError
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.core import security
from app.core.config import settings
from app.core.db import async_session_maker
from app.models import TokenPayload, User

security_scheme = HTTPBearer()
optional_security_scheme = HTTPBearer(auto_error=False)


async def get_db() -> AsyncGenerator[AsyncSession]:
    async with async_session_maker() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_db)]


def get_token(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
) -> str:
    return credentials.credentials


TokenDep = Annotated[str, Depends(get_token)]


def get_optional_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(optional_security_scheme),
) -> str | None:
    if credentials is None:
        return None
    return credentials.credentials


OptionalTokenDep = Annotated[str | None, Depends(get_optional_token)]


async def get_current_user(session: SessionDep, token: TokenDep) -> User:
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        token_data = TokenPayload(**payload)
    except (InvalidTokenError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )
    if not token_data.sub:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )

    try:
        steamid64 = int(token_data.sub)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )

    user = await crud.get_user_by_steamid64(session=session, steamid64=steamid64)
    if not user:
        if settings.ENVIRONMENT == "local":
            user = await crud.get_or_create_user_from_steam(
                session=session,
                steamid64=steamid64,
            )
        else:
            raise HTTPException(status_code=404, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return user


async def get_optional_current_user(
    session: SessionDep,
    token: OptionalTokenDep,
) -> User | None:
    if token is None:
        return None
    return await get_current_user(session=session, token=token)


CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalCurrentUser = Annotated[User | None, Depends(get_optional_current_user)]


def get_current_active_superuser(current_user: CurrentUser) -> User:
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=403, detail="The user doesn't have enough privileges"
        )
    return current_user
