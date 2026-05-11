from typing import Annotated

from fastapi import APIRouter, Header, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.api.deps import SessionDep
from app.models import (
    PlayerSessionConnect,
    PlayerSessionDisconnect,
    PlayerSessionHeartbeat,
    PlayerSessionPublic,
    ServerGroup,
    ServerGroupStatus,
)

router = APIRouter(prefix="/player-sessions", tags=["player-sessions"])


def _resolve_server_group_api_key(
    *,
    x_server_group_key: str | None,
    authorization: str | None,
) -> str | None:
    if x_server_group_key:
        return x_server_group_key
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token:
            return token
    return None


async def _get_server_group_from_api_key(
    *,
    session: AsyncSession,
    x_server_group_key: str | None,
    authorization: str | None = None,
) -> ServerGroup:
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
        raise HTTPException(status_code=403, detail="Server group is invalidated")
    return group


@router.post("/connect", response_model=PlayerSessionPublic)
async def connect_player_session(
    *,
    session: SessionDep,
    payload: PlayerSessionConnect,
    x_server_group_key: Annotated[
        str | None, Header(alias="X-Server-Group-Key")
    ] = None,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> PlayerSessionPublic:
    group = await _get_server_group_from_api_key(
        session=session,
        x_server_group_key=x_server_group_key,
        authorization=authorization,
    )
    try:
        player_session = await crud.connect_player_session(
            session=session,
            group=group,
            payload=payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return crud.to_player_session_public(player_session=player_session)


@router.post("/heartbeat", response_model=PlayerSessionPublic)
async def heartbeat_player_session(
    *,
    session: SessionDep,
    payload: PlayerSessionHeartbeat,
    x_server_group_key: Annotated[
        str | None, Header(alias="X-Server-Group-Key")
    ] = None,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> PlayerSessionPublic:
    group = await _get_server_group_from_api_key(
        session=session,
        x_server_group_key=x_server_group_key,
        authorization=authorization,
    )
    try:
        player_session = await crud.heartbeat_player_session(
            session=session,
            group=group,
            payload=payload,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if player_session is None:
        raise HTTPException(status_code=404, detail="Player session not found")
    return crud.to_player_session_public(player_session=player_session)


@router.post("/disconnect", response_model=PlayerSessionPublic)
async def disconnect_player_session(
    *,
    session: SessionDep,
    payload: PlayerSessionDisconnect,
    x_server_group_key: Annotated[
        str | None, Header(alias="X-Server-Group-Key")
    ] = None,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> PlayerSessionPublic:
    group = await _get_server_group_from_api_key(
        session=session,
        x_server_group_key=x_server_group_key,
        authorization=authorization,
    )
    try:
        player_session = await crud.disconnect_player_session(
            session=session,
            group=group,
            payload=payload,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if player_session is None:
        raise HTTPException(status_code=404, detail="Player session not found")
    return crud.to_player_session_public(player_session=player_session)
