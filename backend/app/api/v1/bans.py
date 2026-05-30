import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app import crud
from app.api.deps import (
    OptionalCurrentUser,
    SessionDep,
    get_current_active_admin,
    get_current_active_superuser,
    user_has_any_role,
)
from app.models import (
    BanCreate,
    BanListQuery,
    BanPublic,
    BansPublic,
    BanUpdate,
    Message,
    User,
    UserRole,
)

router = APIRouter(prefix="/bans", tags=["bans"])

CurrentAdmin = Annotated[User, Depends(get_current_active_admin)]
CurrentSuperuser = Annotated[User, Depends(get_current_active_superuser)]


def _parse_steamid64(value: str) -> int:
    normalized = value.strip()
    if not normalized.isdigit():
        raise HTTPException(status_code=422, detail="steamid64 must be numeric")
    return int(normalized)


def _can_view_ban_admin_fields(current_user: User | None) -> bool:
    if current_user is None:
        return False
    return user_has_any_role(current_user, UserRole.SUPERUSER, UserRole.ADMIN)


@router.get("", response_model=BansPublic, response_model_exclude_unset=True)
async def read_bans(
    session: SessionDep,
    query: Annotated[BanListQuery, Query()],
    current_user: OptionalCurrentUser,
) -> BansPublic:
    include_admin_fields = _can_view_ban_admin_fields(current_user)
    bans, count = await crud.read_bans(session=session, query=query)
    return BansPublic(
        data=[
            crud.to_ban_list_item_public(
                ban=ban,
                player=player,
                updated_by_player=updated_by_player,
                server=server,
                include_admin_fields=include_admin_fields,
            )
            for ban, player, updated_by_player, server in bans
        ],
        count=count,
    )


@router.post("", response_model=BanPublic, response_model_exclude_unset=True)
async def create_ban(
    *,
    session: SessionDep,
    body: BanCreate,
    current_user: CurrentAdmin,
) -> BanPublic:
    steamid64 = _parse_steamid64(body.steamid64)
    player = await crud.get_player_by_steamid64(session=session, steamid64=steamid64)
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found")

    ban = await crud.create_manual_ban(
        session=session,
        body=body,
        steamid64=steamid64,
        updated_by_steamid64=current_user.steamid64,
    )
    updated_by_player = await crud.get_player_by_steamid64(
        session=session,
        steamid64=current_user.steamid64,
    )
    return crud.to_ban_public(
        ban=ban,
        player=player,
        updated_by_player=updated_by_player,
        include_admin_fields=True,
    )


@router.get(
    "/{ban_uuid}",
    response_model=BanPublic,
    response_model_exclude_unset=True,
)
async def read_ban(
    session: SessionDep,
    ban_uuid: uuid.UUID,
    current_user: OptionalCurrentUser,
) -> BanPublic:
    ban_with_player = await crud.get_ban_by_uuid(
        session=session,
        ban_uuid=ban_uuid,
    )
    if ban_with_player is None:
        raise HTTPException(status_code=404, detail="Ban not found")
    include_admin_fields = _can_view_ban_admin_fields(current_user)
    ban, player, updated_by_player, server = ban_with_player
    return crud.to_ban_public(
        ban=ban,
        player=player,
        updated_by_player=updated_by_player,
        server=server,
        include_admin_fields=include_admin_fields,
    )


@router.patch(
    "/{ban_uuid}",
    response_model=BanPublic,
    response_model_exclude_unset=True,
)
async def patch_ban(
    *,
    session: SessionDep,
    ban_uuid: uuid.UUID,
    body: BanUpdate,
    current_user: CurrentAdmin,
) -> BanPublic:
    ban_with_player = await crud.get_ban_by_uuid(session=session, ban_uuid=ban_uuid)
    if ban_with_player is None:
        raise HTTPException(status_code=404, detail="Ban not found")

    ban, player, _updated_by_player, server = ban_with_player
    ban = await crud.update_ban(
        session=session,
        ban=ban,
        body=body,
        updated_by_steamid64=current_user.steamid64,
    )
    updated_by_player = await crud.get_player_by_steamid64(
        session=session,
        steamid64=current_user.steamid64,
    )
    return crud.to_ban_public(
        ban=ban,
        player=player,
        updated_by_player=updated_by_player,
        server=server,
        include_admin_fields=True,
    )


@router.delete("/{ban_uuid}", response_model=Message)
async def delete_ban(
    *,
    session: SessionDep,
    ban_uuid: uuid.UUID,
    _current_user: CurrentSuperuser,
) -> Message:
    ban_with_player = await crud.get_ban_by_uuid(session=session, ban_uuid=ban_uuid)
    if ban_with_player is None:
        raise HTTPException(status_code=404, detail="Ban not found")

    ban, _player, _updated_by_player, _server = ban_with_player
    if ban.id is not None:
        raise HTTPException(
            status_code=409,
            detail="Only bans without a GlobalAPI id can be deleted",
        )

    await crud.delete_ban(session=session, ban=ban)
    return Message(message="Ban deleted successfully")
