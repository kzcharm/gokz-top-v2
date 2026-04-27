import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query

from app import crud
from app.api.deps import AdminServerPrincipal, AdminServerPrincipalDep, SessionDep
from app.models import (
    AdminServerAccessPublic,
    AdminServerGroupsPublic,
    AdminServerRole,
    Message,
    ServerGlobalapiAdminPublic,
    ServerGlobalapiAdminServersPublic,
    ServerGlobalapiAdminUpdate,
    ServerGlobalapiListQuery,
    ServerGroupApiKeyPublic,
    ServerGroupCreate,
    ServerGroupDependencyCounts,
    ServerGroupPublic,
    ServerGroupStatus,
    ServerGroupUpdate,
    ServerListQuery,
    ServerPublic,
    ServersPublic,
    ServerUpdate,
    get_datetime_utc,
)

router = APIRouter(prefix="/admin/servers", tags=["admin-servers"])


def _ensure_group_access(
    *,
    principal: AdminServerPrincipal,
    group_id: uuid.UUID | None,
) -> None:
    if principal.role == AdminServerRole.ROOT_ADMIN or group_id is None:
        return
    if group_id not in principal.owned_group_ids:
        raise HTTPException(status_code=403, detail="Server group is not owned by user")


def _ensure_public_server_access(
    *,
    principal: AdminServerPrincipal,
    group_id: uuid.UUID | None,
) -> None:
    if principal.role == AdminServerRole.ROOT_ADMIN:
        return
    if group_id is None or group_id not in principal.owned_group_ids:
        raise HTTPException(status_code=403, detail="Server is not owned by user")


def _dependency_conflict_detail(
    counts: ServerGroupDependencyCounts,
) -> dict[str, object]:
    return {
        "message": "Server group has dependencies",
        "dependencies": counts.model_dump(),
    }


@router.get("/access", response_model=AdminServerAccessPublic)
async def read_admin_server_access(
    principal: AdminServerPrincipalDep,
) -> AdminServerAccessPublic:
    return AdminServerAccessPublic(
        role=principal.role,
        can_approve_servers=principal.can_approve_servers,
        owned_group_count=len(principal.owned_group_ids),
    )


@router.get("/globalapi", response_model=ServerGlobalapiAdminServersPublic)
async def read_admin_globalapi_servers(
    *,
    session: SessionDep,
    principal: AdminServerPrincipalDep,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=1000)] = 50,
    q: Annotated[str | None, Query(max_length=255)] = None,
    owner_steamid64: Annotated[int | None, Query()] = None,
    approval_status: Annotated[int | None, Query(ge=0, le=1)] = None,
    group_id: uuid.UUID | None = None,
    sort_by: Annotated[
        Literal["id", "server", "updated_at", "created_at"],
        Query(),
    ] = "id",
    sort_order: Annotated[Literal["asc", "desc"], Query()] = "desc",
) -> ServerGlobalapiAdminServersPublic:
    effective_owner = (
        None if principal.role == AdminServerRole.ROOT_ADMIN else principal.user.steamid64
    )
    query = ServerGlobalapiListQuery(
        offset=offset,
        limit=limit,
        group_id=group_id,
        name=q,
        owner_steamid64=owner_steamid64 if effective_owner is None else effective_owner,
        approval_status=approval_status,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    servers, count = await crud.read_server_globalapi_for_admin(
        session=session,
        query=query,
        owner_steamid64=effective_owner,
    )
    return ServerGlobalapiAdminServersPublic(
        data=[
            crud.to_server_globalapi_admin_public(server=server)
            for server in servers
        ],
        count=count,
    )


@router.patch(
    "/globalapi/{server_id}",
    response_model=ServerGlobalapiAdminPublic,
)
async def update_admin_globalapi_server(
    *,
    session: SessionDep,
    principal: AdminServerPrincipalDep,
    server_id: int,
    server_in: ServerGlobalapiAdminUpdate,
) -> ServerGlobalapiAdminPublic:
    server = await crud.get_server_globalapi_by_id(session=session, id=server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="GlobalAPI server not found")
    if (
        principal.role != AdminServerRole.ROOT_ADMIN
        and server.owner_steamid64 != principal.user.steamid64
    ):
        raise HTTPException(status_code=403, detail="GlobalAPI server is not owned by user")

    update_data = server_in.model_dump(exclude_unset=True)
    if "group_id" in update_data:
        group_id = update_data["group_id"]
        _ensure_group_access(principal=principal, group_id=group_id)
        if group_id is not None:
            group = await crud.get_server_group_by_id(session=session, group_id=group_id)
            if group is None:
                raise HTTPException(status_code=404, detail="Server group not found")
        server.group_id = group_id

    if "approval_status" in update_data:
        if not principal.can_approve_servers:
            raise HTTPException(status_code=403, detail="Cannot approve servers")
        server.approval_status = update_data["approval_status"]
        server.approved_by_steamid64 = (
            principal.user.steamid64 if server.approval_status == 1 else 0
        )

    server.updated_at = get_datetime_utc()
    session.add(server)
    await session.commit()
    await session.refresh(server)
    return crud.to_server_globalapi_admin_public(server=server)


@router.get("/public", response_model=ServersPublic)
async def read_admin_public_servers(
    *,
    session: SessionDep,
    principal: AdminServerPrincipalDep,
    query: Annotated[ServerListQuery, Query()],
) -> ServersPublic:
    owned_group_ids = (
        None
        if principal.role == AdminServerRole.ROOT_ADMIN
        else principal.owned_group_ids
    )
    servers, count = await crud.read_servers(
        session=session,
        query=query,
        owned_group_ids=owned_group_ids,
    )
    return ServersPublic(
        data=[crud.to_server_public(server=server) for server in servers],
        count=count,
    )


@router.patch("/public/{server_id}", response_model=ServerPublic)
async def update_admin_public_server(
    *,
    session: SessionDep,
    principal: AdminServerPrincipalDep,
    server_id: uuid.UUID,
    server_in: ServerUpdate,
) -> ServerPublic:
    server = await crud.get_server_by_id(
        session=session,
        server_id=server_id,
        include_invalidated_group=True,
    )
    if server is None:
        raise HTTPException(status_code=404, detail="Server not found")
    _ensure_public_server_access(principal=principal, group_id=server.group_id)

    update_data = server_in.model_dump(exclude_unset=True)
    if "group_id" in update_data:
        if (
            principal.role != AdminServerRole.ROOT_ADMIN
            and update_data["group_id"] is None
        ):
            raise HTTPException(status_code=403, detail="Server group is required")
        _ensure_group_access(principal=principal, group_id=update_data["group_id"])

    try:
        server = await crud.update_server(
            session=session,
            server=server,
            server_in=server_in,
        )
    except ValueError as exc:
        if str(exc) == "Server already exists":
            raise HTTPException(
                status_code=409,
                detail="Server already exists",
            ) from exc
        raise HTTPException(status_code=404, detail="Server group not found") from exc
    return crud.to_server_public(server=server)


@router.delete("/public/{server_id}", response_model=Message)
async def delete_admin_public_server(
    *,
    session: SessionDep,
    principal: AdminServerPrincipalDep,
    server_id: uuid.UUID,
) -> Message:
    server = await crud.get_server_by_id(
        session=session,
        server_id=server_id,
        include_invalidated_group=True,
    )
    if server is None:
        raise HTTPException(status_code=404, detail="Server not found")
    _ensure_public_server_access(principal=principal, group_id=server.group_id)
    await crud.delete_server(session=session, server=server)
    return Message(message="Server deleted successfully")


@router.get("/groups", response_model=AdminServerGroupsPublic)
async def read_admin_server_groups(
    *,
    session: SessionDep,
    principal: AdminServerPrincipalDep,
) -> AdminServerGroupsPublic:
    owner_steamid64 = (
        None if principal.role == AdminServerRole.ROOT_ADMIN else principal.user.steamid64
    )
    groups, counts = await crud.read_server_groups_for_admin(
        session=session,
        owner_steamid64=owner_steamid64,
    )
    return AdminServerGroupsPublic(
        data=[
            crud.to_admin_server_group_public(
                group=group,
                server_count=counts.get(group.id, 0),
            )
            for group in groups
        ],
        count=len(groups),
    )


@router.post("/groups", response_model=ServerGroupApiKeyPublic)
async def create_admin_server_group(
    *,
    session: SessionDep,
    principal: AdminServerPrincipalDep,
    group_in: ServerGroupCreate,
) -> ServerGroupApiKeyPublic:
    try:
        group, api_key = await crud.create_server_group(
            session=session,
            group_in=group_in,
            owner_steamid64=principal.user.steamid64,
            initial_status=ServerGroupStatus.VALIDATED,
        )
    except ValueError as exc:
        if str(exc) == "Server group owner is permanently blocked":
            raise HTTPException(
                status_code=403,
                detail="Server group owner is permanently blocked",
            ) from exc
        raise HTTPException(
            status_code=409,
            detail="Server group already exists",
        ) from exc

    return ServerGroupApiKeyPublic(
        group=crud.to_server_group_public(group=group, server_count=0),
        api_key=api_key,
    )


@router.patch("/groups/{group_id}", response_model=ServerGroupPublic)
async def update_admin_server_group(
    *,
    session: SessionDep,
    principal: AdminServerPrincipalDep,
    group_id: uuid.UUID,
    group_in: ServerGroupUpdate,
) -> ServerGroupPublic:
    _ensure_group_access(principal=principal, group_id=group_id)
    update_data = group_in.model_dump(exclude_unset=True)
    update_data.pop("status", None)
    group_in = ServerGroupUpdate.model_validate(update_data)

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
            status_code=409,
            detail="Server group already exists",
        ) from exc
    counts = await crud.get_server_group_dependency_counts(
        session=session,
        group_id=group.id,
    )
    return crud.to_server_group_public(group=group, server_count=counts.servers)


@router.put("/groups/{group_id}/api-key", response_model=ServerGroupApiKeyPublic)
async def rotate_admin_server_group_api_key(
    *,
    session: SessionDep,
    principal: AdminServerPrincipalDep,
    group_id: uuid.UUID,
) -> ServerGroupApiKeyPublic:
    _ensure_group_access(principal=principal, group_id=group_id)
    group = await crud.get_server_group_by_id(session=session, group_id=group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Server group not found")
    group, api_key = await crud.rotate_server_group_api_key(
        session=session,
        group=group,
    )
    counts = await crud.get_server_group_dependency_counts(
        session=session,
        group_id=group.id,
    )
    return ServerGroupApiKeyPublic(
        group=crud.to_server_group_public(group=group, server_count=counts.servers),
        api_key=api_key,
    )


@router.delete("/groups/{group_id}", response_model=Message)
async def delete_admin_server_group(
    *,
    session: SessionDep,
    principal: AdminServerPrincipalDep,
    group_id: uuid.UUID,
) -> Message:
    _ensure_group_access(principal=principal, group_id=group_id)
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
            detail=_dependency_conflict_detail(counts),
        ) from exc
    return Message(message="Server group deleted successfully")
