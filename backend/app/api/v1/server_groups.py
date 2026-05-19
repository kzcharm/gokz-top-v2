import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import col, func, select

from app import crud
from app.api.deps import SessionDep, get_current_active_superuser
from app.models import (
    Message,
    Server,
    ServerGroupApiKeyPublic,
    ServerGroupCreate,
    ServerGroupPublic,
    ServerGroupsPublic,
    ServerGroupUpdate,
    User,
)

router = APIRouter(prefix="/server-groups", tags=["server-groups"])

CurrentSuperuser = Annotated[User, Depends(get_current_active_superuser)]


async def _get_server_count(*, session: SessionDep, group_id: uuid.UUID) -> int:
    statement = (
        select(func.count()).select_from(Server).where(col(Server.group_id) == group_id)
    )
    return (await session.exec(statement)).one()


@router.get("", response_model=ServerGroupsPublic)
async def read_server_groups(session: SessionDep) -> Any:
    groups, counts = await crud.read_server_groups(session=session)
    return ServerGroupsPublic(
        data=[
            crud.to_server_group_public(
                group=group,
                server_count=counts.get(group.id, 0),
            )
            for group in groups
        ],
        count=len(groups),
    )


@router.post(
    "",
    dependencies=[Depends(get_current_active_superuser)],
    response_model=ServerGroupApiKeyPublic,
)
async def create_server_group(
    *,
    session: SessionDep,
    group_in: ServerGroupCreate,
    current_user: CurrentSuperuser,
) -> Any:
    try:
        group, api_key = await crud.create_server_group(
            session=session,
            group_in=group_in,
            owner_steamid64=current_user.steamid64,
        )
    except ValueError as exc:
        if str(exc) == "Server group owner is permanently blocked":
            raise HTTPException(
                status_code=403,
                detail="Server group owner is permanently blocked",
            ) from exc
        raise HTTPException(
            status_code=409, detail="Server group already exists"
        ) from exc

    return ServerGroupApiKeyPublic(
        group=crud.to_server_group_public(group=group, server_count=0),
        api_key=api_key,
    )


@router.patch(
    "/{group_id}",
    dependencies=[Depends(get_current_active_superuser)],
    response_model=ServerGroupPublic,
)
async def update_server_group(
    *,
    session: SessionDep,
    group_id: uuid.UUID,
    group_in: ServerGroupUpdate,
    current_user: CurrentSuperuser,
) -> Any:
    del current_user
    group = await crud.get_server_group_by_id(session=session, group_id=group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Server group not found")

    try:
        group = await crud.update_server_group(
            session=session,
            group=group,
            group_in=group_in,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=409, detail="Server group already exists"
        ) from exc

    return crud.to_server_group_public(
        group=group,
        server_count=await _get_server_count(session=session, group_id=group.id),
    )


@router.put(
    "/{group_id}/api-key",
    dependencies=[Depends(get_current_active_superuser)],
    response_model=ServerGroupApiKeyPublic,
)
async def rotate_server_group_api_key(
    *,
    session: SessionDep,
    group_id: uuid.UUID,
    current_user: CurrentSuperuser,
) -> Any:
    del current_user
    group = await crud.get_server_group_by_id(session=session, group_id=group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Server group not found")

    group, api_key = await crud.rotate_server_group_api_key(
        session=session,
        group=group,
    )
    return ServerGroupApiKeyPublic(
        group=crud.to_server_group_public(
            group=group,
            server_count=await _get_server_count(session=session, group_id=group.id),
        ),
        api_key=api_key,
    )


@router.delete(
    "/{group_id}",
    dependencies=[Depends(get_current_active_superuser)],
    response_model=Message,
)
async def delete_server_group(
    *,
    session: SessionDep,
    group_id: uuid.UUID,
    current_user: CurrentSuperuser,
) -> Message:
    del current_user
    group = await crud.get_server_group_by_id(session=session, group_id=group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Server group not found")
    try:
        await crud.delete_server_group(session=session, group=group)
    except ValueError as exc:
        counts = await crud.get_server_group_dependency_counts(
            session=session,
            group_id=group.id,
        )
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Server group has dependencies",
                "dependencies": counts.model_dump(),
            },
        ) from exc
    return Message(message="Server group deleted successfully")
