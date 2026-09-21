import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app import crud
from app.api.deps import AdminServerPrincipal, AdminServerPrincipalDep, SessionDep
from app.models import (
    AdminServerAccessPublic,
    AdminServerGroupsPublic,
    AdminServerGroupUpdate,
    AdminServerListQuery,
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
    ServerPublic,
    ServersPublic,
    ServerUpdate,
    get_datetime_utc,
)
from app.services.gokz_localdb_export import (
    get_gokz_localdb_export_stats,
    gzip_sql_stream,
    iter_gokz_localdb_mysql_sql,
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
        None
        if principal.role == AdminServerRole.ROOT_ADMIN
        else principal.user.steamid64
    )
    query = ServerGlobalapiListQuery(
        offset=offset,
        limit=limit,
        group_id=group_id,
        q=q,
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
            crud.to_server_globalapi_admin_public(server=server) for server in servers
        ],
        count=count,
    )


@router.get(
    "/globalapi/records/export",
    response_class=StreamingResponse,
    responses={
        200: {
            "content": {
                "application/gzip": {"schema": {"type": "string", "format": "binary"}}
            },
            "description": "Gzip-compressed GOKZ LocalDB MySQL import script",
        }
    },
)
async def export_admin_globalapi_server_records(
    *,
    session: SessionDep,
    principal: AdminServerPrincipalDep,
    server_id: Annotated[list[int], Query(min_length=1, max_length=20)],
) -> StreamingResponse:
    server_ids = sorted(set(server_id))
    for selected_server_id in server_ids:
        server = await crud.get_server_globalapi_by_id(
            session=session,
            id=selected_server_id,
        )
        if server is None:
            raise HTTPException(
                status_code=404,
                detail=f"GlobalAPI server {selected_server_id} not found",
            )
        if (
            principal.role != AdminServerRole.ROOT_ADMIN
            and server.owner_steamid64 != principal.user.steamid64
        ):
            raise HTTPException(
                status_code=403,
                detail=f"GlobalAPI server {selected_server_id} is not owned by user",
            )
    stats = await get_gokz_localdb_export_stats(
        session=session,
        server_ids=server_ids,
    )
    if stats.exportable_rows == 0:
        raise HTTPException(
            status_code=422,
            detail="Selected servers have no valid GOKZ LocalDB-compatible records",
        )

    id_suffix = "-".join(str(value) for value in server_ids)
    filename = f"gokz-localdb-records-{id_suffix}.sql.gz"
    sql_chunks = iter_gokz_localdb_mysql_sql(
        session=session,
        server_ids=server_ids,
        stats=stats,
    )
    return StreamingResponse(
        gzip_sql_stream(sql_chunks),
        media_type="application/gzip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Exported-Record-Count": str(stats.exportable_rows),
            "X-Skipped-Record-Count": str(stats.skipped_rows),
        },
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
        raise HTTPException(
            status_code=403, detail="GlobalAPI server is not owned by user"
        )

    update_data = server_in.model_dump(exclude_unset=True)
    if "owner_steamid64" in update_data:
        if principal.role != AdminServerRole.ROOT_ADMIN:
            raise HTTPException(status_code=403, detail="Cannot change server owner")
        owner_steamid64 = update_data["owner_steamid64"]
        owner_id = int(owner_steamid64) if owner_steamid64 is not None else None
        if owner_id is not None:
            owner = await crud.get_player_by_steamid64(
                session=session,
                steamid64=owner_id,
            )
            if owner is None:
                raise HTTPException(status_code=404, detail="Player not found")
        server.owner_steamid64 = owner_id

    if "group_id" in update_data:
        group_id = update_data["group_id"]
        _ensure_group_access(principal=principal, group_id=group_id)
        if group_id is not None:
            group = await crud.get_server_group_by_id(
                session=session, group_id=group_id
            )
            if group is None:
                raise HTTPException(status_code=404, detail="Server group not found")
        server.group_id = group_id

    if "approval_status" in update_data:
        if not principal.can_approve_servers:
            raise HTTPException(status_code=403, detail="Cannot approve servers")
        server.approval_status = update_data["approval_status"]
        server.approved_by_steamid64 = (
            principal.user.steamid64 if server.approval_status == 1 else None
        )

    if "name" in update_data:
        name = update_data["name"]
        server.name = name.strip() if name and name.strip() else None

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
    query: Annotated[AdminServerListQuery, Query()],
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
        is_public=query.is_public,
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
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=1000)] = 50,
    sort_by: Annotated[
        Literal["name", "last_api_key_used_at", "created_at", "updated_at"],
        Query(),
    ] = "name",
    sort_order: Annotated[Literal["asc", "desc"], Query()] = "asc",
) -> AdminServerGroupsPublic:
    owner_steamid64 = (
        None
        if principal.role == AdminServerRole.ROOT_ADMIN
        else principal.user.steamid64
    )
    groups, counts, count = await crud.read_server_groups_for_admin(
        session=session,
        owner_steamid64=owner_steamid64,
        offset=offset,
        limit=limit,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return AdminServerGroupsPublic(
        data=[
            crud.to_admin_server_group_public(
                group=group,
                server_count=counts.get(group.id, 0),
            )
            for group in groups
        ],
        count=count,
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
    group_in: AdminServerGroupUpdate,
) -> ServerGroupPublic:
    _ensure_group_access(principal=principal, group_id=group_id)
    update_data = group_in.model_dump(exclude_unset=True)
    update_data.pop("status", None)
    owner_was_set = "owner_steamid64" in update_data
    owner_steamid64 = update_data.pop("owner_steamid64", None)
    group_update = ServerGroupUpdate.model_validate(update_data)

    group = await crud.get_server_group_by_id(session=session, group_id=group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Server group not found")
    if owner_was_set:
        if principal.role != AdminServerRole.ROOT_ADMIN:
            raise HTTPException(
                status_code=403, detail="Cannot change server group owner"
            )
        owner_id = int(owner_steamid64) if owner_steamid64 is not None else None
        if owner_id is not None:
            owner = await crud.get_player_by_steamid64(
                session=session,
                steamid64=owner_id,
            )
            if owner is None:
                raise HTTPException(status_code=404, detail="Player not found")
        group.owner_steamid64 = owner_id
    try:
        group = await crud.update_server_group(
            session=session,
            group=group,
            group_in=group_update,
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
