from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app import crud
from app.api.deps import SessionDep, get_current_active_superuser
from app.models import (
    AdminPlayerSessionIpLinkMatchMode,
    AdminPlayerSessionIpLinksPublic,
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
    player_steamid64 = None
    if query.player_steamid64:
        normalized_steamid64 = query.player_steamid64.strip()
        if not normalized_steamid64.isdigit():
            raise HTTPException(status_code=422, detail="player_steamid64 must be numeric")
        player_steamid64 = int(normalized_steamid64)

    rows, count = await crud.read_admin_player_sessions(
        session=session,
        offset=query.offset,
        limit=query.limit,
        player_steamid64=player_steamid64,
        server_group_id=query.server_group_id,
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


@router.get(
    "/player-sessions/ip-links",
    response_model=AdminPlayerSessionIpLinksPublic,
)
async def read_admin_player_session_ip_links(
    *,
    session: SessionDep,
    _current_user: CurrentSuperuser,
    steamid64: Annotated[str, Query()],
    match_mode: Annotated[AdminPlayerSessionIpLinkMatchMode, Query()] = "exact_ip",
    from_at: Annotated[datetime | None, Query(alias="from")] = None,
    to_at: Annotated[datetime | None, Query(alias="to")] = None,
    days: Annotated[int, Query(ge=1, le=3650)] = 365,
    depth: Annotated[int, Query(ge=1, le=5)] = 1,
    max_players_per_bucket: Annotated[int, Query(ge=1, le=500)] = 50,
) -> AdminPlayerSessionIpLinksPublic:
    normalized_steamid64 = steamid64.strip()
    if not normalized_steamid64.isdigit():
        raise HTTPException(status_code=422, detail="steamid64 must be numeric")
    if from_at is not None and to_at is not None and from_at > to_at:
        raise HTTPException(status_code=422, detail="from must be before to")

    result = await crud.read_admin_player_session_ip_links(
        session=session,
        steamid64=int(normalized_steamid64),
        match_mode=match_mode,
        from_at=from_at,
        to_at=to_at,
        days=days,
        depth=depth,
        max_players_per_bucket=max_players_per_bucket,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Player not found")
    return result
