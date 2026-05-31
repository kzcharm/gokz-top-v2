import logging
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from app import crud
from app.api.deps import CurrentUser, SessionDep, get_current_active_superuser
from app.api.v1.player_sessions import _resolve_server_group_api_key
from app.crud.server import mark_server_group_api_key_used
from app.models import (
    Message,
    ServerCreate,
    ServerGroupStatus,
    ServerHistoryPublic,
    ServerHistoryQuery,
    ServerListQuery,
    ServerPublic,
    ServersPublic,
    ServerStatusPut,
    ServerUpdate,
    User,
)
from app.services.server_events import broadcast_server_update
from app.services.server_query import (
    ServerQueryError,
    query_server_a2s_info,
    validate_server_addition_info,
)

router = APIRouter(prefix="/servers", tags=["servers"])
logger = logging.getLogger(__name__)

CurrentSuperuser = Annotated[User, Depends(get_current_active_superuser)]


@router.put("/status", response_model=ServerPublic)
async def put_server_status(
    *,
    session: SessionDep,
    payload: ServerStatusPut,
    x_server_group_key: Annotated[
        str | None, Header(alias="X-Server-Group-Key")
    ] = None,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> Any:
    api_key = _resolve_server_group_api_key(
        x_server_group_key=x_server_group_key,
        authorization=authorization,
    )
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing server group API key")

    group = await crud.get_server_group_by_api_key(
        session=session,
        api_key=api_key,
    )
    if group is None:
        raise HTTPException(status_code=401, detail="Invalid server group API key")
    if group.status == ServerGroupStatus.INVALIDATED:
        logger.warning(
            "Rejected server heartbeat ip=%s port=%s group_id=%s reason=group_invalidated",
            payload.ip,
            payload.port,
            group.id,
        )
        raise HTTPException(status_code=403, detail="Server group is invalidated")
    mark_server_group_api_key_used(session=session, group=group)

    existing_server = await crud.get_server_by_endpoint(
        session=session,
        ip=payload.ip,
        port=payload.port,
    )
    previous_public = (
        crud.to_server_public(server=existing_server).model_dump(mode="json")
        if existing_server is not None
        else None
    )

    try:
        server = await crud.upsert_server_from_plugin_heartbeat(
            session=session,
            group=group,
            payload=payload,
        )
    except ValueError as exc:
        if str(exc) == "Server is disabled":
            logger.warning(
                "Rejected server heartbeat ip=%s port=%s group_id=%s reason=server_disabled",
                payload.ip,
                payload.port,
                group.id,
            )
            raise HTTPException(status_code=403, detail="Server is not enabled") from exc
        if str(exc) == "Server does not belong to this server group":
            logger.warning(
                "Rejected server heartbeat ip=%s port=%s group_id=%s reason=group_mismatch",
                payload.ip,
                payload.port,
                group.id,
            )
            raise HTTPException(
                status_code=403,
                detail="Server does not belong to this server group",
            ) from exc
        raise
    next_public = crud.to_server_public(server=server).model_dump(mode="json")
    if previous_public != next_public:
        await broadcast_server_update(server)
    return crud.to_server_public(server=server)


@router.get("", response_model=ServersPublic)
async def read_servers(
    session: SessionDep,
    query: Annotated[ServerListQuery, Query()],
) -> Any:
    servers, count = await crud.read_servers(session=session, query=query)
    return ServersPublic(
        data=[crud.to_server_public(server=server) for server in servers],
        count=count,
    )


@router.get("/{server_id}/history", response_model=ServerHistoryPublic)
async def read_server_history(
    *,
    session: SessionDep,
    server_id: uuid.UUID,
    query: Annotated[ServerHistoryQuery, Query()],
) -> Any:
    server = await crud.get_server_by_id(session=session, server_id=server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="Server not found")

    history = await crud.read_server_history(
        session=session,
        server_id=server_id,
        query=query,
    )
    return ServerHistoryPublic(data=history, count=len(history))


@router.get("/{server_id}", response_model=ServerPublic)
async def read_server(*, session: SessionDep, server_id: uuid.UUID) -> Any:
    server = await crud.get_server_by_id(session=session, server_id=server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="Server not found")
    return crud.to_server_public(server=server)


@router.post(
    "",
    response_model=ServerPublic,
)
async def create_server(
    *,
    session: SessionDep,
    server_in: ServerCreate,
    current_user: CurrentUser,
) -> Any:
    try:
        queried = await query_server_a2s_info(ip=server_in.ip, port=server_in.port)
        validate_server_addition_info(queried)
        server = await crud.create_server(
            session=session,
            server_in=server_in,
            steamid64=current_user.steamid64,
            queried_hostname=queried.hostname,
            queried_map=queried.map_name,
            queried_player_count=queried.player_count,
            queried_max_players=queried.max_players,
            queried_players=queried.players,
        )
    except ServerQueryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        detail = "Server group not found"
        if str(exc) == "Server already exists":
            detail = "Server already exists"
            raise HTTPException(status_code=409, detail=detail) from exc
        if str(exc) == "Server is disabled":
            raise HTTPException(status_code=403, detail="Server is disabled") from exc
        raise HTTPException(status_code=404, detail=detail) from exc
    return crud.to_server_public(server=server)


@router.patch(
    "/{server_id}",
    dependencies=[Depends(get_current_active_superuser)],
    response_model=ServerPublic,
)
async def update_server(
    *,
    session: SessionDep,
    server_id: uuid.UUID,
    server_in: ServerUpdate,
    current_user: CurrentSuperuser,
) -> Any:
    del current_user
    server = await crud.get_server_by_id(
        session=session,
        server_id=server_id,
        include_invalidated_group=True,
    )
    if server is None:
        raise HTTPException(status_code=404, detail="Server not found")

    new_ip = server_in.ip if server_in.ip is not None else server.ip
    new_port = server_in.port if server_in.port is not None else server.port
    endpoint_changed = new_ip != server.ip or new_port != server.port

    queried = None
    if endpoint_changed:
        try:
            queried = await query_server_a2s_info(ip=new_ip, port=new_port)
        except ServerQueryError as exc:
            raise HTTPException(
                status_code=422, detail="Unable to query server"
            ) from exc

    try:
        server = await crud.update_server(
            session=session,
            server=server,
            server_in=server_in,
        )
    except ValueError as exc:
        if str(exc) == "Server already exists":
            raise HTTPException(
                status_code=409, detail="Server already exists"
            ) from exc
        raise HTTPException(status_code=404, detail="Server group not found") from exc

    if queried is not None:
        server = await crud.record_a2s_success(
            session=session,
            server=server,
            observed_at=queried.observed_at,
            hostname=queried.hostname,
            map_name=queried.map_name,
            player_count=queried.player_count,
            max_players=queried.max_players,
            players=queried.players,
        )

    return crud.to_server_public(server=server)


@router.delete(
    "/{server_id}",
    dependencies=[Depends(get_current_active_superuser)],
    response_model=Message,
)
async def delete_server(
    *,
    session: SessionDep,
    server_id: uuid.UUID,
    current_user: CurrentSuperuser,
) -> Message:
    del current_user
    server = await crud.get_server_by_id(session=session, server_id=server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="Server not found")
    await crud.delete_server(session=session, server=server)
    return Message(message="Server deleted successfully")
