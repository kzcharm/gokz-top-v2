import logging
import uuid
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query
from sqlalchemy import func
from sqlmodel import col, select

from app import crud
from app.api.deps import CurrentUser, SessionDep, get_current_active_superuser
from app.api.v1.player_sessions import _resolve_server_group_api_key
from app.crud import player as player_crud
from app.crud.server import mark_server_group_api_key_used
from app.models import (
    Message,
    Player,
    PlayerServerActivityPublic,
    PlayerServerActivityRatingPublic,
    PlayerServerActivitySummaryPublic,
    PlayerServerRecentPlaytimePublic,
    Record,
    ServerCreate,
    ServerGlobalapi,
    ServerGroup,
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
from app.models.leaderboard_player import scale_public_rating
from app.models.utils import get_datetime_utc
from app.services.server_events import broadcast_server_update
from app.services.server_query import (
    ServerQueryError,
    query_server_a2s_info,
    validate_server_addition_info,
)

router = APIRouter(prefix="/servers", tags=["servers"])
logger = logging.getLogger(__name__)

CurrentSuperuser = Annotated[User, Depends(get_current_active_superuser)]


_SECONDS_PER_HOUR = 3600
_SECOND_PRECISION = Decimal("0.001")


def _to_public_seconds(value: Decimal) -> float:
    return float(value.quantize(_SECOND_PRECISION))


async def _read_recent_record_playtime(
    *,
    session: SessionDep,
    steamid64: int,
    server_group_id: uuid.UUID,
    requested_hours: int,
) -> PlayerServerRecentPlaytimePublic:
    requested_seconds = Decimal(requested_hours * _SECONDS_PER_HOUR)
    window_seconds = Decimal("0")
    on_server_seconds = Decimal("0")
    statement = (
        select(col(Record.time), col(ServerGlobalapi.group_id))
        .join(ServerGlobalapi, col(Record.server_id) == col(ServerGlobalapi.id))
        .where(col(Record.steamid64) == steamid64)
        .order_by(
            col(Record.created_at).desc(),
            col(Record.id).desc().nulls_last(),
            col(Record.uuid).desc(),
        )
    )
    rows = (await session.exec(statement)).all()
    for record_time, record_group_id in rows:
        if window_seconds >= requested_seconds:
            break
        record_seconds = Decimal(record_time)
        if record_seconds <= 0:
            continue
        consumed_seconds = min(record_seconds, requested_seconds - window_seconds)
        window_seconds += consumed_seconds
        if record_group_id == server_group_id:
            on_server_seconds += consumed_seconds

    ratio = (
        round(float(on_server_seconds / window_seconds), 3)
        if window_seconds > 0
        else 0
    )
    return PlayerServerRecentPlaytimePublic(
        requested_hours=requested_hours,
        window_seconds=_to_public_seconds(window_seconds),
        on_server_seconds=_to_public_seconds(on_server_seconds),
        ratio=ratio,
    )


async def _read_player_server_activity_summary(
    *,
    session: SessionDep,
    player: Player,
    server_group: ServerGroup,
    requested_hours: int,
) -> PlayerServerActivitySummaryPublic:
    record_day = func.date_trunc("day", Record.created_at)
    activity_statement = (
        select(
            func.min(Record.created_at),
            func.min(Record.created_at).filter(
                col(ServerGlobalapi.group_id) == server_group.id
            ),
            func.count(func.distinct(record_day)),
            func.coalesce(func.sum(Record.time), Decimal("0")),
        )
        .join(ServerGlobalapi, col(Record.server_id) == col(ServerGlobalapi.id))
        .where(col(Record.steamid64) == player.steamid64)
    )
    first_seen_at, first_server_record_at, active_days, total_playtime_seconds = (
        await session.exec(activity_statement)
    ).one()
    ratings_by_player = await crud.load_player_ratings_by_scope(
        session=session,
        steamid64s=[player.steamid64],
    )
    ratings_by_scope = ratings_by_player.get(player.steamid64, {})
    ratings = [
        PlayerServerActivityRatingPublic(
            mode=scope.value,
            rating=scale_public_rating(raw_rating) or 0,
            is_primary=scope == player.primary_scope,
        )
        for scope, raw_rating in sorted(
            ratings_by_scope.items(),
            key=lambda item: item[0].scope_id,
        )
    ]
    return PlayerServerActivitySummaryPublic(
        steam_id=str(player.steamid64),
        server_id=server_group.custom_id,
        generated_at=get_datetime_utc(),
        ratings=ratings,
        activity=PlayerServerActivityPublic(
            first_seen_at=first_seen_at,
            first_server_record_at=first_server_record_at,
            active_days=int(active_days or 0),
            total_playtime_seconds=_to_public_seconds(
                Decimal(total_playtime_seconds or 0)
            ),
            recent_playtime=await _read_recent_record_playtime(
                session=session,
                steamid64=player.steamid64,
                server_group_id=server_group.id,
                requested_hours=requested_hours,
            ),
        ),
    )


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


@router.get(
    "/{server_id}/players/{identifier:path}/activity-summary",
    response_model=PlayerServerActivitySummaryPublic,
)
async def read_player_server_activity_summary(
    *,
    session: SessionDep,
    server_id: Annotated[str, Path(min_length=1, max_length=25)],
    identifier: Annotated[str, Path(min_length=1)],
    recent_hours: Annotated[int, Query(ge=1, le=500)] = 50,
) -> PlayerServerActivitySummaryPublic:
    try:
        normalized_server_id = crud.normalize_custom_id(server_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Server group not found") from exc
    if normalized_server_id is None:
        raise HTTPException(status_code=404, detail="Server group not found")

    server_group_statement = select(ServerGroup).where(
        col(ServerGroup.custom_id) == normalized_server_id
    )
    server_group = (await session.exec(server_group_statement)).first()
    if server_group is None:
        raise HTTPException(status_code=404, detail="Server group not found")

    player = await player_crud.get_player_by_identifier(
        session=session,
        identifier=identifier,
    )
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found")

    return await _read_player_server_activity_summary(
        session=session,
        player=player,
        server_group=server_group,
        requested_hours=recent_hours,
    )


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
