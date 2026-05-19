from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import col, func, select

from app import crud
from app.api.deps import (
    CurrentUser,
    SessionDep,
    get_current_active_superuser,
    user_has_role,
)
from app.models import (
    User,
    UserPublic,
    UserRole,
    UsersListQuery,
    UsersPublic,
    UserUpdate,
    get_datetime_utc,
)

router = APIRouter(prefix="/users", tags=["users"])


def _parse_steamid64(user_id: str) -> int:
    try:
        return int(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid steamid64") from exc


@router.get(
    "",
    dependencies=[Depends(get_current_active_superuser)],
    response_model=UsersPublic,
)
async def read_users(
    session: SessionDep,
    query: Annotated[UsersListQuery, Query()],
) -> Any:
    """
    Retrieve users.
    """
    count_statement = select(func.count()).select_from(User)
    count = (await session.exec(count_statement)).one()

    sort_column = col(User.created_at)
    if query.sort_by == "last_visited_at":
        sort_column = col(User.last_visited_at)

    sort_direction = (
        sort_column.asc() if query.sort_order == "asc" else sort_column.desc()
    )
    statement = (
        select(User)
        .order_by(sort_direction.nullslast(), col(User.steamid64).desc())
        .offset(query.skip)
        .limit(query.limit)
    )
    users = (await session.exec(statement)).all()

    return UsersPublic(
        data=[await crud.to_user_public(session=session, user=user) for user in users],
        count=count,
    )


@router.get("/me", response_model=UserPublic)
async def read_user_me(current_user: CurrentUser, session: SessionDep) -> Any:
    """
    Get current user.
    """
    current_user.last_visited_at = get_datetime_utc()
    session.add(current_user)
    await session.commit()
    await session.refresh(current_user)
    return await crud.to_user_public(session=session, user=current_user)


@router.get("/{user_id}", response_model=UserPublic)
async def read_user_by_id(
    user_id: str, session: SessionDep, current_user: CurrentUser
) -> Any:
    """
    Get a specific user by steamid64.
    """
    steamid64 = _parse_steamid64(user_id)
    user = await session.get(User, steamid64)
    if user == current_user:
        return await crud.to_user_public(session=session, user=user)
    if not user_has_role(current_user, UserRole.SUPERUSER):
        raise HTTPException(
            status_code=403,
            detail="The user doesn't have enough privileges",
        )
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return await crud.to_user_public(session=session, user=user)


@router.patch(
    "/{user_id}",
    dependencies=[Depends(get_current_active_superuser)],
    response_model=UserPublic,
)
async def update_user(
    *,
    session: SessionDep,
    user_id: str,
    user_in: UserUpdate,
) -> Any:
    """
    Update a user.
    """
    steamid64 = _parse_steamid64(user_id)
    db_user = await session.get(User, steamid64)
    if not db_user:
        raise HTTPException(
            status_code=404,
            detail="The user with this id does not exist in the system",
        )

    db_user = await crud.update_user(session=session, db_user=db_user, user_in=user_in)
    return await crud.to_user_public(session=session, user=db_user)
