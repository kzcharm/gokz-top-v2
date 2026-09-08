import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app import crud
from app.api.deps import SessionDep, get_current_active_superuser
from app.models import (
    AdminPollPublic,
    AdminPollsPublic,
    PollCreate,
    PollListQuery,
    PollUpdate,
    User,
)

router = APIRouter(prefix="/admin/polls", tags=["admin-polls"])
CurrentSuperuser = Annotated[User, Depends(get_current_active_superuser)]


@router.get("", response_model=AdminPollsPublic)
async def read_admin_polls(
    *,
    session: SessionDep,
    query: Annotated[PollListQuery, Query()],
    _user: CurrentSuperuser,
) -> AdminPollsPublic:
    polls, count = await crud.read_polls(session=session, query=query)
    return AdminPollsPublic(
        data=[
            await crud.to_poll_public(session, poll, _user.steamid64, admin=True)
            for poll in polls
        ],
        count=count,
    )


@router.post("", response_model=AdminPollPublic)
async def create_admin_poll(
    *, session: SessionDep, poll_in: PollCreate, _user: CurrentSuperuser
) -> AdminPollPublic:
    poll = await crud.create_poll(session, poll_in, _user.steamid64)
    return await crud.to_poll_public(session, poll, _user.steamid64, admin=True)  # type: ignore[return-value]


@router.patch("/{poll_id}", response_model=AdminPollPublic)
async def update_admin_poll(
    *,
    session: SessionDep,
    poll_id: uuid.UUID,
    poll_in: PollUpdate,
    _user: CurrentSuperuser,
) -> AdminPollPublic:
    poll = await crud.get_poll(session, poll_id)
    if poll is None:
        raise HTTPException(status_code=404, detail="Poll not found")
    try:
        poll = await crud.update_poll(session, poll, poll_in)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return await crud.to_poll_public(session, poll, _user.steamid64, admin=True)  # type: ignore[return-value]


@router.delete("/{poll_id}")
async def delete_admin_poll(
    *, session: SessionDep, poll_id: uuid.UUID, _user: CurrentSuperuser
) -> dict[str, str]:
    poll = await crud.get_poll(session, poll_id)
    if poll is None:
        raise HTTPException(status_code=404, detail="Poll not found")
    await crud.delete_poll(session, poll)
    return {"message": "Poll deleted successfully"}
