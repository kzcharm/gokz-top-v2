from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import (
    ServerGlobalapi,
    ServerGlobalapiAdminPublic,
    ServerGlobalapiCompatPublicV0,
    ServerGlobalapiListQuery,
)


async def read_server_globalapi(
    *,
    session: AsyncSession,
    query: ServerGlobalapiListQuery,
) -> tuple[list[ServerGlobalapi], int]:
    statement = select(ServerGlobalapi)

    if query.id:
        statement = statement.where(col(ServerGlobalapi.id).in_(query.id))
    if query.group_id is not None:
        statement = statement.where(col(ServerGlobalapi.group_id) == query.group_id)
    if query.port is not None:
        statement = statement.where(col(ServerGlobalapi.port) == query.port)
    if query.ip is not None:
        statement = statement.where(col(ServerGlobalapi.ip) == query.ip)
    if query.name is not None:
        statement = statement.where(col(ServerGlobalapi.name).ilike(f"%{query.name}%"))
    if query.owner_steamid64 is not None:
        statement = statement.where(
            col(ServerGlobalapi.owner_steamid64) == query.owner_steamid64
        )
    if query.approval_status is not None:
        statement = statement.where(
            col(ServerGlobalapi.approval_status) == query.approval_status
        )

    sort_column = col(ServerGlobalapi.id)
    if query.sort_by == "server":
        sort_column = col(ServerGlobalapi.name)
    elif query.sort_by == "updated_at":
        sort_column = col(ServerGlobalapi.updated_at)
    elif query.sort_by == "created_at":
        sort_column = col(ServerGlobalapi.created_at)

    if query.sort_order == "desc":
        statement = statement.order_by(sort_column.desc(), col(ServerGlobalapi.id).asc())
    else:
        statement = statement.order_by(sort_column.asc(), col(ServerGlobalapi.id).asc())
    all_rows = list((await session.exec(statement)).all())
    count = len(all_rows)
    return all_rows[query.offset : query.offset + query.limit], count


async def read_server_globalapi_for_admin(
    *,
    session: AsyncSession,
    query: ServerGlobalapiListQuery,
    owner_steamid64: int | None = None,
) -> tuple[list[ServerGlobalapi], int]:
    effective_query = query
    if owner_steamid64 is not None:
        effective_query = query.model_copy(update={"owner_steamid64": owner_steamid64})
    return await read_server_globalapi(session=session, query=effective_query)


async def get_server_globalapi_by_id(
    *,
    session: AsyncSession,
    id: int,
) -> ServerGlobalapi | None:
    return await session.get(ServerGlobalapi, id)


async def read_server_globalapi_by_name(
    *,
    session: AsyncSession,
    server_name: str,
) -> list[ServerGlobalapi]:
    statement = (
        select(ServerGlobalapi)
        .where(col(ServerGlobalapi.name).ilike(f"%{server_name}%"))
        .order_by(col(ServerGlobalapi.id).asc())
    )
    return list((await session.exec(statement)).all())


def to_server_globalapi_compat_public_v0(
    *,
    server: ServerGlobalapi,
) -> ServerGlobalapiCompatPublicV0:
    return ServerGlobalapiCompatPublicV0(
        id=server.id,
        port=server.port,
        ip=server.ip,
        name=server.name,
        owner_steamid64=str(server.owner_steamid64),
    )


def to_server_globalapi_admin_public(
    *,
    server: ServerGlobalapi,
) -> ServerGlobalapiAdminPublic:
    return ServerGlobalapiAdminPublic(
        id=server.id,
        group_id=server.group_id,
        port=server.port,
        ip=server.ip,
        name=server.name,
        owner_steamid64=str(server.owner_steamid64),
        approval_status=server.approval_status,
        approved_by_steamid64=str(server.approved_by_steamid64),
        created_at=server.created_at,
        updated_at=server.updated_at,
        synced_at=server.synced_at,
    )
