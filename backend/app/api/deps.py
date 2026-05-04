import uuid
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidTokenError
from pydantic import ValidationError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.core import security
from app.core.config import settings
from app.core.db import async_session_maker
from app.models import (
    AdminServerRole,
    ServerGlobalapi,
    ServerGroup,
    TokenPayload,
    User,
    UserRole,
    normalize_user_roles,
)

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


def user_has_role(user: User, role: UserRole) -> bool:
    return role in normalize_user_roles(user.roles)


def user_has_any_role(user: User, *roles: UserRole) -> bool:
    normalized_roles = set(normalize_user_roles(user.roles))
    return any(role in normalized_roles for role in roles)


def require_roles(*roles: UserRole) -> Callable[..., User]:
    def dependency(
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        if not user_has_any_role(current_user, *roles):
            raise HTTPException(
                status_code=403,
                detail="The user doesn't have enough privileges",
            )
        return current_user

    return dependency


def get_current_active_superuser(current_user: CurrentUser) -> User:
    return require_roles(UserRole.SUPERUSER)(current_user)


def get_current_active_map_admin(current_user: CurrentUser) -> User:
    return require_roles(UserRole.SUPERUSER, UserRole.MAP_ADMIN)(current_user)


@dataclass(frozen=True)
class AdminServerPrincipal:
    user: User
    role: AdminServerRole
    owned_group_ids: frozenset[uuid.UUID]

    @property
    def can_approve_servers(self) -> bool:
        return self.role == AdminServerRole.ROOT_ADMIN


async def get_admin_server_principal(
    session: SessionDep,
    current_user: CurrentUser,
) -> AdminServerPrincipal:
    groups_statement = select(ServerGroup.id).where(
        col(ServerGroup.owner_steamid64) == current_user.steamid64
    )
    owned_group_ids = frozenset((await session.exec(groups_statement)).all())

    if user_has_role(current_user, UserRole.SUPERUSER):
        return AdminServerPrincipal(
            user=current_user,
            role=AdminServerRole.ROOT_ADMIN,
            owned_group_ids=owned_group_ids,
        )

    owned_globalapi_statement = select(ServerGlobalapi.id).where(
        col(ServerGlobalapi.owner_steamid64) == current_user.steamid64,
        col(ServerGlobalapi.approval_status) == 1,
    )
    if (await session.exec(owned_globalapi_statement)).first() is None:
        raise HTTPException(
            status_code=403,
            detail="The user doesn't have enough server privileges",
        )

    return AdminServerPrincipal(
        user=current_user,
        role=AdminServerRole.SERVER_OWNER,
        owned_group_ids=owned_group_ids,
    )


AdminServerPrincipalDep = Annotated[
    AdminServerPrincipal,
    Depends(get_admin_server_principal),
]
