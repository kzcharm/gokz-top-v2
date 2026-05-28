from typing import Annotated

from fastapi import APIRouter, Header, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.api.deps import SessionDep
from app.core.config import settings
from app.models import (
    Ban,
    PlayerSessionBanEnforcementBanPublic,
    PlayerSessionBanEnforcementPublic,
    PlayerSessionConnect,
    PlayerSessionConnectPublic,
    PlayerSessionDisconnect,
    PlayerSessionHeartbeat,
    PlayerSessionPublic,
    ServerGroup,
    ServerGroupStatus,
)

router = APIRouter(prefix="/player-sessions", tags=["player-sessions"])


def _normalize_kick_message_language(client_language: str | None) -> str:
    language = (client_language or "").strip().lower()
    if language in {
        "chi",
        "chinese",
        "schinese",
        "tchinese",
        "zh",
        "zh-cn",
        "zh-hans",
        "zh-hant",
        "zho",
    }:
        return "chi"
    if language in {"ru", "rus", "russian"}:
        return "ru"
    return "en"


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


def _ban_enforcement_for_ban(
    *,
    ban: Ban,
    client_language: str | None,
) -> PlayerSessionBanEnforcementPublic:
    frontend_host = settings.FRONTEND_HOST.rstrip("/")
    detail_url = f"{frontend_host}/bans?q={ban.uuid}"
    appeal_url = f"{frontend_host}/bans"
    ban_type = ban.ban_type.value
    expires_at = ban.expires_at.date().isoformat() if ban.expires_at else None
    reason = ban.notes.strip() if ban.notes and ban.notes.strip() else "-"
    language = _normalize_kick_message_language(client_language)
    kick_message_lines = {
        "en": (
            "You are banned from this server and cannot join!",
            f"Ban type: {ban_type}",
            f"Expires: {expires_at or 'permanent'}",
            f"Reason: {reason}",
            f"Appeal: visit {appeal_url}",
        ),
        "chi": (
            "您已被服务器封禁，禁止进入服务器！",
            f"封禁类型：{ban_type}",
            f"到期时间：{expires_at or '永久'}",
            f"封禁原因：{reason}",
            f"申诉解封：请访问 {appeal_url}",
        ),
        "ru": (
            "Вам запрещен вход на этот сервер!",
            f"Тип блокировки: {ban_type}",
            f"Истекает: {expires_at or 'навсегда'}",
            f"Причина: {reason}",
            f"Апелляция: посетите {appeal_url}",
        ),
    }
    kick_message = "\n".join(kick_message_lines[language])
    return PlayerSessionBanEnforcementPublic(
        ban=PlayerSessionBanEnforcementBanPublic(
            uuid=ban.uuid,
            ban_type=ban.ban_type,
            expires_at=ban.expires_at,
        ),
        detail_url=detail_url,
        kick_message=kick_message,
    )


@router.post("/connect", response_model=PlayerSessionConnectPublic)
async def connect_player_session(
    *,
    session: SessionDep,
    payload: PlayerSessionConnect,
    x_server_group_key: Annotated[
        str | None, Header(alias="X-Server-Group-Key")
    ] = None,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> PlayerSessionConnectPublic:
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
    session_public = crud.to_player_session_public(player_session=player_session)
    active_ban = await crud.get_newest_active_ban_for_player(
        session=session,
        steamid64=player_session.player_steamid64,
    )
    return PlayerSessionConnectPublic(
        **session_public.model_dump(),
        ban_enforcement=(
            _ban_enforcement_for_ban(
                ban=active_ban,
                client_language=payload.client_language,
            )
            if active_ban is not None
            else None
        ),
    )


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
