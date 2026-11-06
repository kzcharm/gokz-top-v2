import asyncio
import json
import secrets
import time
import uuid
from datetime import timedelta
from typing import Annotated, Any, Literal

import jwt
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import CurrentUser, SessionDep, TokenDep
from app.core.config import settings
from app.core.db import async_session_maker
from app.core.security import ALGORITHM
from app.models import (
    KZMode,
    Map,
    Player,
    RecordReplay,
    ReplayListQuery,
    User,
    UserRole,
    get_datetime_utc,
)
from app.models.server import ServersPublic
from app.models.web_gokz import (
    MapName,
    WebCourse,
    WebExchange,
    WebFinish,
    WebIdentity,
    WebLaunch,
    WebMap,
    WebMode,
    WebPlayer,
    WebRecord,
    WebRecords,
    WebSession,
    WebTime,
)
from app.services import r2_storage
from app.services.player_webhooks import build_player_avatar_url
from app.services.record_replay_catalog import list_replays
from app.services.web_gokz import Member, rooms

router = APIRouter(prefix="/web-gokz", tags=["web-gokz"])
AUDIENCE = "web-gokz"
# The dedicated service owns short-lived launch codes as well as room state.
launch_codes: dict[str, tuple[int, float]] = {}


async def identity(session: AsyncSession, steamid64: int) -> WebIdentity:
    player = await session.get(Player, steamid64)
    return WebIdentity(
        steamid64=str(steamid64),
        name=(player.alias or player.name) if player else str(steamid64),
        avatarfull=build_player_avatar_url(player.avatar_hash) if player else None,
        avatar_hash=player.avatar_hash if player else None,
    )


async def authenticate(session: AsyncSession, token: str) -> User:
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[ALGORITHM],
            audience=AUDIENCE,
            options={"require": ["exp", "sub", "aud"]},
        )
        user = await session.get(User, int(payload["sub"]))
    except (jwt.InvalidTokenError, ValueError, TypeError, KeyError):
        raise HTTPException(401, "Sign in to GOKZ.TOP again.")
    if user is None or not user.is_active:
        raise HTTPException(401, "This account is unavailable.")
    return user


async def web_user(session: SessionDep, token: TokenDep) -> User:
    return await authenticate(session, token)


WebUser = Annotated[User, Depends(web_user)]


@router.post("/session", response_model=WebSession)
async def create_session(session: SessionDep, user: CurrentUser) -> WebSession:
    token = jwt.encode(
        {
            "sub": str(user.steamid64),
            "aud": AUDIENCE,
            "exp": get_datetime_utc() + timedelta(hours=12),
        },
        settings.SECRET_KEY,
        algorithm=ALGORITHM,
    )
    return WebSession(
        access_token=token, player=await identity(session, user.steamid64)
    )


@router.post("/launch", response_model=WebLaunch)
async def create_launch(user: CurrentUser) -> WebLaunch:
    now = time.monotonic()
    for code, (_, expires) in list(launch_codes.items()):
        if expires <= now:
            del launch_codes[code]
    if (
        len(launch_codes) >= 1000
        or sum(owner == user.steamid64 for owner, _ in launch_codes.values()) >= 10
    ):
        raise HTTPException(429, "Please retry launching Web GOKZ in a minute.")
    code = secrets.token_urlsafe(32)
    launch_codes[code] = (user.steamid64, now + 60)
    return WebLaunch(code=code)


@router.post("/session/exchange", response_model=WebSession)
async def exchange_launch(
    body: WebExchange, request: Request, session: SessionDep
) -> WebSession:
    if request.headers.get("origin") != (settings.REPLAY_VIEWER_HOST or "").rstrip("/"):
        raise HTTPException(403, "Open this link in Web GOKZ.")
    entry = launch_codes.pop(body.code, None)
    if entry is None or entry[1] <= time.monotonic():
        raise HTTPException(401, "This play link expired. Launch Web GOKZ again.")
    user = await session.get(User, entry[0])
    if user is None or not user.is_active:
        raise HTTPException(401, "This account is unavailable.")
    return await create_session(session, user)


@router.get("/me", response_model=WebIdentity)
async def read_me(session: SessionDep, user: WebUser) -> WebIdentity:
    return await identity(session, user.steamid64)


@router.get("/maps")
async def read_maps() -> dict[str, Any]:
    maps = next(iter(rooms.values())).maps if rooms else {}
    return {
        "data": [
            {"name": name, "bsp_sha256": version} for name, version in maps.items()
        ],
        "count": len(maps),
    }


@router.get("/maps/{map_name}/reference")
async def read_reference(
    map_name: MapName, session: SessionDep, mode: WebMode = "NKZ"
) -> dict[str, str | None]:
    for preferred in (KZMode(mode), None):
        ids, _ = await list_replays(
            session,
            ReplayListQuery(
                map_name=map_name,
                mode=preferred,
                stage=0,
                teleports=0,
                limit=1,
            ),
        )
        if ids:
            replay = await session.get(RecordReplay, ids[0])
            if replay is not None and replay.available:
                url = (
                    r2_storage.build_public_url(replay.key)
                    if replay.storage == "r2"
                    else f"{settings.BACKEND_PUBLIC_URL.rstrip('/')}{settings.API_V1_STR}/replays/{ids[0]}"
                )
                return {"url": url}
    return {"url": None}


@router.get("/rooms")
async def read_rooms() -> dict[str, Any]:
    return {"data": [room.public() for room in rooms.values()], "count": len(rooms)}


@router.get("/servers", response_model=ServersPublic)
async def read_servers(session: SessionDep) -> ServersPublic:
    servers = [room.server_public() for room in rooms.values()]
    maps = (
        await session.exec(
            select(Map).where(
                col(Map.name).in_([room.map_name for room in rooms.values()])
            )
        )
    ).all()
    tiers = {map_.name: map_.difficulty for map_ in maps}
    for server in servers:
        if server.live_status:
            server.map_tier = tiers.get(server.live_status.map or "")
    return ServersPublic(data=servers, count=len(servers))


def record_public(row: Any, player: WebIdentity) -> WebRecord:
    record, course, map_ = row
    return WebRecord(
        id=record.id,
        player=player,
        map_name=map_.name,
        map_version=map_.version,
        engine_version=record.engine_version,
        mode=record.mode,
        course=course.course,
        time_ms=record.time_ms,
        teleports=record.teleports,
        created_at=record.created_at,
        source="room" if record.room_id else "solo",
    )


async def saved_record(session: AsyncSession, record: WebTime) -> WebRecord:
    course = await session.get(WebCourse, record.course_id)
    assert course is not None
    map_ = await session.get(WebMap, course.map_id)
    return record_public(
        (record, course, map_), await identity(session, record.player_steamid64)
    )


@router.post("/records", response_model=WebRecord)
async def submit_record(
    body: WebFinish, session: SessionDep, user: WebUser
) -> WebRecord:
    existing = (
        await session.exec(
            select(WebTime).where(
                WebTime.player_steamid64 == user.steamid64,
                WebTime.submission_id == body.submission_id,
            )
        )
    ).first()
    if existing:
        public = await saved_record(session, existing)
        if (
            any(
                getattr(public, key) != getattr(body, key)
                for key in (
                    "map_name",
                    "map_version",
                    "engine_version",
                    "mode",
                    "course",
                    "time_ms",
                    "teleports",
                )
            )
            or existing.room_id != body.room_id
            or existing.room_generation != body.room_generation
        ):
            raise HTTPException(
                409, "This submission ID already belongs to a different finish."
            )
        return public
    if body.room_id is not None:
        room = rooms.get(body.room_id)
        if (
            not room
            or str(user.steamid64) not in room.members
            or room.generation != body.room_generation
            or room.map_name != body.map_name
            or room.maps.get(body.map_name) != body.map_version
        ):
            raise HTTPException(
                409, "The room or map has changed. This finish cannot be submitted."
            )
    elif body.room_generation is not None:
        raise HTTPException(422, "A solo finish cannot have a room generation.")
    recent = (
        await session.exec(
            select(func.count())
            .select_from(WebTime)
            .where(
                WebTime.player_steamid64 == user.steamid64,
                WebTime.created_at > get_datetime_utc() - timedelta(minutes=1),
            )
        )
    ).one()
    if recent >= 60:
        raise HTTPException(429, "Too many finishes. Please retry in a minute.")
    await session.execute(
        insert(WebPlayer).values(steamid64=user.steamid64).on_conflict_do_nothing()
    )
    map_id = (
        await session.execute(
            insert(WebMap)
            .values(id=uuid.uuid7(), name=body.map_name, version=body.map_version)
            .on_conflict_do_update(
                index_elements=["name", "version"], set_={"name": body.map_name}
            )
            .returning(col(WebMap.id))
        )
    ).scalar_one()
    course_id = (
        await session.execute(
            insert(WebCourse)
            .values(id=uuid.uuid7(), map_id=map_id, course=body.course)
            .on_conflict_do_update(
                index_elements=["map_id", "course"], set_={"course": body.course}
            )
            .returning(col(WebCourse.id))
        )
    ).scalar_one()
    record_id = (
        await session.execute(
            insert(WebTime)
            .values(
                id=uuid.uuid7(),
                submission_id=body.submission_id,
                player_steamid64=user.steamid64,
                course_id=course_id,
                mode=body.mode,
                engine_version=body.engine_version,
                time_ms=body.time_ms,
                teleports=body.teleports,
                room_id=body.room_id,
                room_generation=body.room_generation,
                created_at=get_datetime_utc(),
            )
            .on_conflict_do_nothing(
                index_elements=["player_steamid64", "submission_id"]
            )
            .returning(col(WebTime.id))
        )
    ).scalar_one_or_none()
    if record_id is None:
        await session.rollback()
        return await submit_record(body, session, user)
    await session.commit()
    record = await session.get(WebTime, record_id)
    assert record is not None
    public = await saved_record(session, record)
    room = rooms.get(body.room_id) if body.room_id is not None else None
    if room and room.generation == body.room_generation:
        member = room.members.get(str(user.steamid64))
        if member:
            member.finished = True
            member.running = False
            if member.state:
                member.state.update(
                    timer_running=False,
                    timer_paused=False,
                    time_ms=body.time_ms,
                    teleports=body.teleports,
                    progress=100,
                )
        room.broadcast(
            {
                "type": "finish",
                "player": public.player.model_dump(),
                "map_name": body.map_name,
                "mode": body.mode,
                "time_ms": body.time_ms,
                "teleports": body.teleports,
                "record_id": str(record.id),
                "generation": str(room.generation),
            }
        )
    return public


async def leaderboard(
    session: AsyncSession,
    map_name: str,
    mode: WebMode,
    course: int,
    record_type: str,
    map_version: str,
    engine_version: str,
    limit: int,
    offset: int,
    steamid64: int | None = None,
) -> WebRecords:
    query = (
        select(
            WebTime.id,
            func.row_number()
            .over(
                partition_by=col(WebTime.player_steamid64),
                order_by=(col(WebTime.time_ms), col(WebTime.id)),
            )
            .label("rank"),
        )
        .join(WebCourse, col(WebCourse.id) == WebTime.course_id)
        .join(WebMap, col(WebMap.id) == WebCourse.map_id)
        .where(
            WebMap.name == map_name,
            WebMap.version == map_version,
            WebCourse.course == course,
            WebTime.mode == mode,
            WebTime.engine_version == engine_version,
        )
    )
    if record_type == "PRO":
        query = query.where(WebTime.teleports == 0)
    if steamid64 is not None:
        query = query.where(WebTime.player_steamid64 == steamid64)
    ranked = query.subquery()
    count = (
        await session.exec(
            select(func.count()).select_from(ranked).where(ranked.c.rank == 1)
        )
    ).one()
    rows = (
        await session.exec(
            select(WebTime, WebCourse, WebMap)
            .join(WebCourse, col(WebCourse.id) == WebTime.course_id)
            .join(WebMap, col(WebMap.id) == WebCourse.map_id)
            .join(ranked, ranked.c.id == WebTime.id)
            .where(ranked.c.rank == 1)
            .order_by(col(WebTime.time_ms), col(WebTime.id))
            .offset(offset)
            .limit(limit)
        )
    ).all()
    players = (
        (
            await session.exec(
                select(Player).where(
                    col(Player.steamid64).in_([row[0].player_steamid64 for row in rows])
                )
            )
        ).all()
        if rows
        else []
    )
    identities = {
        p.steamid64: WebIdentity(
            steamid64=str(p.steamid64),
            name=p.alias or p.name,
            avatarfull=build_player_avatar_url(p.avatar_hash),
            avatar_hash=p.avatar_hash,
        )
        for p in players
    }
    return WebRecords(
        data=[
            record_public(
                row,
                identities.get(
                    row[0].player_steamid64,
                    WebIdentity(
                        steamid64=str(row[0].player_steamid64),
                        name=str(row[0].player_steamid64),
                    ),
                ),
            )
            for row in rows
        ],
        count=count,
    )


@router.get("/records", response_model=WebRecords)
async def read_records(
    session: SessionDep,
    map_name: str,
    map_version: str,
    engine_version: str,
    mode: WebMode = "NKZ",
    course: Annotated[int, Query(ge=0, le=1000)] = 0,
    type: Literal["NUB", "PRO"] = "NUB",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> WebRecords:
    return await leaderboard(
        session,
        map_name,
        mode,
        course,
        type,
        map_version,
        engine_version,
        limit,
        offset,
    )


@router.get("/records/pb")
async def read_pb(
    session: SessionDep,
    user: WebUser,
    map_name: str,
    map_version: str,
    engine_version: str,
    mode: WebMode = "NKZ",
    course: Annotated[int, Query(ge=0, le=1000)] = 0,
    type: Literal["NUB", "PRO"] = "NUB",
) -> dict[str, WebRecord | None]:
    results = await leaderboard(
        session,
        map_name,
        mode,
        course,
        type,
        map_version,
        engine_version,
        1,
        0,
        user.steamid64,
    )
    return {"record": results.data[0] if results.data else None}


@router.websocket("/rooms/{room_id}/ws")
async def room_socket(websocket: WebSocket, room_id: int) -> None:
    origin = websocket.headers.get("origin")
    if origin not in settings.all_cors_origins or room_id not in rooms:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    member = None
    sender = None
    room = rooms[room_id]
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=5)
        if len(raw) > 4096:
            raise ValueError("Authentication message is too large.")
        auth = json.loads(raw)
        if (
            not isinstance(auth, dict)
            or auth.get("type") != "auth"
            or not isinstance(auth.get("token"), str)
        ):
            raise ValueError("Sign in before joining a room.")
        async with async_session_maker() as session:
            user = await authenticate(session, auth["token"])
            member = Member(
                await identity(session, user.steamid64),
                admin=bool(set(user.roles) & {UserRole.ADMIN, UserRole.SUPERUSER}),
            )
        room.join(member)

        async def send_messages() -> None:
            assert member is not None
            while True:
                message = await member.queue.get()
                if message["type"] == "disconnect":
                    await websocket.close(code=1013)
                    return
                await asyncio.wait_for(websocket.send_json(message), timeout=5)

        sender = asyncio.create_task(send_messages())
        expires = jwt.decode(
            auth["token"],
            settings.SECRET_KEY,
            algorithms=[ALGORITHM],
            audience=AUDIENCE,
        )["exp"]
        while time.time() < expires:
            # Uvicorn's WebSocket ping timeout detects dead peers; paused players stay joined.
            raw = await asyncio.wait_for(
                websocket.receive_text(), timeout=max(0, expires - time.time())
            )
            if len(raw) > 4096:
                raise ValueError("Message is too large.")
            try:
                payload = json.loads(raw)
                if not isinstance(payload, dict):
                    raise ValueError("Expected a message object.")
                room.receive(member, payload, time.time())
            except ValueError as error:
                member.send({"type": "error", "message": str(error)[:400]})
    except (ValueError, HTTPException, TimeoutError) as error:
        await websocket.send_json({"type": "error", "message": str(error)[:400]})
    except WebSocketDisconnect:
        pass
    finally:
        if member:
            room.leave(member)
        if sender:
            sender.cancel()
            await asyncio.gather(sender, return_exceptions=True)
        try:
            await websocket.close()
        except RuntimeError:
            pass
