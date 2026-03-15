from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import (
    ServerGlobalapi,
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
        statement = statement.where(ServerGlobalapi.id.in_(query.id))
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

    statement = statement.order_by(col(ServerGlobalapi.id).asc())
    all_rows = list((await session.exec(statement)).all())
    count = len(all_rows)
    return all_rows[query.offset : query.offset + query.limit], count


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
