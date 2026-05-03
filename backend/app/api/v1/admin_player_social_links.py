import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app import crud
from app.api.deps import SessionDep, get_current_active_superuser
from app.models import (
    AdminPlayerSocialLinkCreate,
    AdminPlayerSocialLinkListQuery,
    AdminPlayerSocialLinkPublic,
    AdminPlayerSocialLinksPublic,
    AdminPlayerSocialLinkUpdate,
    User,
)

router = APIRouter(prefix="/admin", tags=["admin-player-social-links"])

CurrentSuperuser = Annotated[User, Depends(get_current_active_superuser)]


def _parse_steamid64(steamid64: str) -> int:
    normalized = steamid64.strip()
    if not normalized.isdigit():
        raise HTTPException(status_code=422, detail="steamid64 must be numeric")
    return int(normalized)


@router.get(
    "/player-social-links",
    response_model=AdminPlayerSocialLinksPublic,
)
async def read_admin_player_social_links(
    *,
    session: SessionDep,
    query: Annotated[AdminPlayerSocialLinkListQuery, Query()],
    _current_user: CurrentSuperuser,
) -> AdminPlayerSocialLinksPublic:
    steamid64 = _parse_steamid64(query.steamid64) if query.steamid64 else None
    rows, count = await crud.read_admin_player_social_links(
        session=session,
        offset=query.offset,
        limit=query.limit,
        steamid64=steamid64,
        platform=query.platform,
        verified=query.verified,
        sort_by=query.sort_by,
        sort_order=query.sort_order,
    )
    return AdminPlayerSocialLinksPublic(
        data=[
            crud.to_admin_player_social_link_public(link=link, player=player)
            for link, player in rows
        ],
        count=count,
    )


@router.post(
    "/player-social-links",
    response_model=AdminPlayerSocialLinkPublic,
)
async def create_admin_player_social_link(
    *,
    session: SessionDep,
    body: AdminPlayerSocialLinkCreate,
    _current_user: CurrentSuperuser,
) -> AdminPlayerSocialLinkPublic:
    steamid64 = _parse_steamid64(body.player_steamid64)
    player = await crud.get_player_by_steamid64(
        session=session,
        steamid64=steamid64,
    )
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found")

    try:
        link = await crud.create_player_social_link(
            session=session,
            player_steamid64=steamid64,
            url=body.url,
            verified=body.verified,
        )
    except crud.PlayerSocialLinkConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return crud.to_admin_player_social_link_public(link=link, player=player)


@router.patch(
    "/player-social-links/{link_id}",
    response_model=AdminPlayerSocialLinkPublic,
)
async def update_admin_player_social_link(
    *,
    session: SessionDep,
    link_id: uuid.UUID,
    body: AdminPlayerSocialLinkUpdate,
    _current_user: CurrentSuperuser,
) -> AdminPlayerSocialLinkPublic:
    link = await crud.get_player_social_link(session=session, id=link_id)
    if link is None:
        raise HTTPException(status_code=404, detail="Social link not found")

    try:
        link = await crud.update_player_social_link(
            session=session,
            link=link,
            url=body.url,
            verified=body.verified,
        )
    except crud.PlayerSocialLinkConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    player = await crud.get_player_by_steamid64(
        session=session,
        steamid64=link.player_steamid64,
    )
    return crud.to_admin_player_social_link_public(link=link, player=player)


@router.delete("/player-social-links/{link_id}")
async def delete_admin_player_social_link(
    *,
    session: SessionDep,
    link_id: uuid.UUID,
    _current_user: CurrentSuperuser,
) -> dict[str, str]:
    link = await crud.get_player_social_link(session=session, id=link_id)
    if link is None:
        raise HTTPException(status_code=404, detail="Social link not found")

    await crud.delete_player_social_link(session=session, link=link)
    return {"message": "Social link deleted successfully"}
