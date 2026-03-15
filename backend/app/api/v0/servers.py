from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app import crud
from app.api.deps import SessionDep
from app.models import ServerGlobalapiCompatPublicV0, ServerGlobalapiListQuery

router = APIRouter(prefix="/servers", tags=["servers"])


@router.get("", response_model=list[ServerGlobalapiCompatPublicV0])
async def read_servers(
    session: SessionDep,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=10000)] = 100,
    id: Annotated[list[int] | None, Query()] = None,
    port: Annotated[int | None, Query(ge=1, le=65535)] = None,
    ip: Annotated[str | None, Query()] = None,
    name: Annotated[str | None, Query()] = None,
    owner_steamid64: Annotated[int | None, Query()] = None,
    approval_status: Annotated[int | None, Query(ge=0, le=1)] = None,
) -> list[ServerGlobalapiCompatPublicV0]:
    servers, _ = await crud.read_server_globalapi(
        session=session,
        query=ServerGlobalapiListQuery(
            offset=offset,
            limit=limit,
            id=id,
            port=port,
            ip=ip,
            name=name,
            owner_steamid64=owner_steamid64,
            approval_status=approval_status,
        ),
    )
    return [
        crud.to_server_globalapi_compat_public_v0(server=server) for server in servers
    ]


@router.get("/name/{server_name}", response_model=list[ServerGlobalapiCompatPublicV0])
async def read_servers_by_name(
    session: SessionDep,
    server_name: str,
) -> list[ServerGlobalapiCompatPublicV0]:
    servers = await crud.read_server_globalapi_by_name(
        session=session,
        server_name=server_name,
    )
    return [
        crud.to_server_globalapi_compat_public_v0(server=server) for server in servers
    ]


@router.get("/{id:int}", response_model=ServerGlobalapiCompatPublicV0)
async def read_server_by_id(
    session: SessionDep,
    id: int,
) -> ServerGlobalapiCompatPublicV0:
    server = await crud.get_server_globalapi_by_id(session=session, id=id)
    if server is None:
        raise HTTPException(status_code=404, detail="Server not found")
    return crud.to_server_globalapi_compat_public_v0(server=server)
