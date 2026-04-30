from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app import crud
from app.api.deps import SessionDep, get_current_active_superuser
from app.models import (
    AdminPlayerSessionListQuery,
    AdminPlayerSessionsPublic,
    User,
)

router = APIRouter(prefix="/admin", tags=["admin-player-sessions"])

CurrentSuperuser = Annotated[User, Depends(get_current_active_superuser)]


@router.get("/player-sessions", response_model=AdminPlayerSessionsPublic)
async def read_admin_player_sessions(
    *,
    session: SessionDep,
    query: Annotated[AdminPlayerSessionListQuery, Query()],
    _current_user: CurrentSuperuser,
) -> AdminPlayerSessionsPublic:
    rows, count = await crud.read_admin_player_sessions(
        session=session,
        offset=query.offset,
        limit=query.limit,
        latest_only=query.latest_only,
        sort_by=query.sort_by,
        sort_order=query.sort_order,
    )
    return AdminPlayerSessionsPublic(
        data=[
            crud.to_admin_player_session_public(
                player_session=player_session,
                player=player,
                server_group=server_group,
            )
            for player_session, player, server_group in rows
        ],
        count=count,
    )
