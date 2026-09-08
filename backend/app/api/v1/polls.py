import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app import crud
from app.api.deps import (
    CurrentUser,
    OptionalCurrentUser,
    SessionDep,
    user_has_any_role,
)
from app.models import (
    PollListQuery,
    PollPublic,
    PollsPublic,
    PollVoteCreate,
    UserRole,
)

router = APIRouter(prefix="/polls", tags=["polls"])


@router.get("", response_model=PollsPublic)
async def read_polls(
    *,
    session: SessionDep,
    current_user: OptionalCurrentUser,
    query: Annotated[PollListQuery, Query()],
) -> PollsPublic:
    polls, count = await crud.read_polls(session=session, query=query)
    is_admin = current_user is not None and user_has_any_role(
        current_user, UserRole.SUPERUSER, UserRole.ADMIN
    )
    return PollsPublic(
        data=[
            await crud.to_poll_public(
                session,
                poll,
                current_user.steamid64 if current_user else None,
                admin=is_admin,
            )
            for poll in polls
        ],
        count=count,
    )


@router.get("/{poll_id}", response_model=PollPublic)
async def read_poll(
    *, session: SessionDep, poll_id: uuid.UUID, current_user: OptionalCurrentUser
) -> PollPublic:
    poll = await crud.get_poll(session, poll_id)
    if poll is None:
        raise HTTPException(status_code=404, detail="Poll not found")
    is_admin = current_user is not None and user_has_any_role(
        current_user, UserRole.SUPERUSER, UserRole.ADMIN
    )
    return await crud.to_poll_public(
        session,
        poll,
        current_user.steamid64 if current_user else None,
        admin=is_admin,
    )


@router.post("/{poll_id}/votes", response_model=PollPublic)
async def vote_poll(
    *,
    session: SessionDep,
    poll_id: uuid.UUID,
    vote_in: PollVoteCreate,
    current_user: CurrentUser,
) -> PollPublic:
    poll = await crud.get_poll(session, poll_id)
    if poll is None:
        raise HTTPException(status_code=404, detail="Poll not found")
    if poll.status.value == "closed" or (
        poll.ends_at is not None and poll.ends_at <= datetime.now(UTC)
    ):
        raise HTTPException(status_code=409, detail="Poll is closed")
    try:
        await crud.cast_vote(session, poll, current_user.steamid64, vote_in.option_ids)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return await crud.to_poll_public(
        session,
        poll,
        current_user.steamid64,
        admin=user_has_any_role(current_user, UserRole.SUPERUSER, UserRole.ADMIN),
    )
