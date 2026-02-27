from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import col, delete, func, select

from app import crud
from app.api.deps import CurrentUser, SessionDep, get_current_active_superuser
from app.models import (
    Item,
    Message,
    User,
    UserPublic,
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
    "/",
    dependencies=[Depends(get_current_active_superuser)],
    response_model=UsersPublic,
)
def read_users(session: SessionDep, skip: int = 0, limit: int = 100) -> Any:
    """
    Retrieve users.
    """
    count_statement = select(func.count()).select_from(User)
    count = session.exec(count_statement).one()

    statement = (
        select(User).order_by(col(User.created_at).desc()).offset(skip).limit(limit)
    )
    users = session.exec(statement).all()

    return UsersPublic(
        data=[crud.to_user_public(session=session, user=user) for user in users],
        count=count,
    )


@router.get("/me", response_model=UserPublic)
def read_user_me(current_user: CurrentUser, session: SessionDep) -> Any:
    """
    Get current user.
    """
    current_user.last_visited_at = get_datetime_utc()
    session.add(current_user)
    session.commit()
    session.refresh(current_user)
    return crud.to_user_public(session=session, user=current_user)


@router.delete("/me", response_model=Message)
def delete_user_me(session: SessionDep, current_user: CurrentUser) -> Any:
    """
    Delete own user.
    """
    if current_user.is_superuser:
        raise HTTPException(
            status_code=403, detail="Super users are not allowed to delete themselves"
        )
    session.delete(current_user)
    session.commit()
    return Message(message="User deleted successfully")


@router.get("/{user_id}", response_model=UserPublic)
def read_user_by_id(
    user_id: str, session: SessionDep, current_user: CurrentUser
) -> Any:
    """
    Get a specific user by steamid64.
    """
    steamid64 = _parse_steamid64(user_id)
    user = session.get(User, steamid64)
    if user == current_user:
        return crud.to_user_public(session=session, user=user)
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=403,
            detail="The user doesn't have enough privileges",
        )
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return crud.to_user_public(session=session, user=user)


@router.patch(
    "/{user_id}",
    dependencies=[Depends(get_current_active_superuser)],
    response_model=UserPublic,
)
def update_user(
    *,
    session: SessionDep,
    user_id: str,
    user_in: UserUpdate,
) -> Any:
    """
    Update a user.
    """
    steamid64 = _parse_steamid64(user_id)
    db_user = session.get(User, steamid64)
    if not db_user:
        raise HTTPException(
            status_code=404,
            detail="The user with this id does not exist in the system",
        )

    db_user = crud.update_user(session=session, db_user=db_user, user_in=user_in)
    return crud.to_user_public(session=session, user=db_user)


@router.delete("/{user_id}", dependencies=[Depends(get_current_active_superuser)])
def delete_user(
    session: SessionDep, current_user: CurrentUser, user_id: str
) -> Message:
    """
    Delete a user.
    """
    steamid64 = _parse_steamid64(user_id)
    user = session.get(User, steamid64)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user == current_user:
        raise HTTPException(
            status_code=403, detail="Super users are not allowed to delete themselves"
        )
    statement = delete(Item).where(col(Item.owner_id) == steamid64)
    session.exec(statement)
    session.delete(user)
    session.commit()
    return Message(message="User deleted successfully")
