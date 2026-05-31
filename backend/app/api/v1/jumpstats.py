import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, File, Header, HTTPException, Query, Request, UploadFile

from app import crud
from app.api.deps import SessionDep
from app.api.v1.player_sessions import _get_server_group_from_api_key
from app.models import (
    Jumpstat,
    JumpstatDetailPublic,
    JumpstatListQuery,
    JumpstatReplayEligibilityPublic,
    JumpstatReplayEligibilityQuery,
    JumpstatsPublic,
    JumpstatVisualizationPublic,
)
from app.services.jump_replay_parser import JumpReplayParseError
from app.services.jump_replay_retention import get_jump_replay_eligibility
from app.services.jumpstat_ingest import JumpReplayIneligibleError, ingest_jump_replay
from app.services.jumpstat_visualization import (
    JumpstatVisualizationUnavailableError,
    get_or_build_jumpstat_visualization,
)

router = APIRouter(prefix="/jumpstats", tags=["jumpstats"])


@router.post("", response_model=JumpstatDetailPublic, status_code=201)
async def create_jumpstat(
    *,
    session: SessionDep,
    replay: Annotated[UploadFile, File()],
    x_server_group_key: Annotated[
        str | None, Header(alias="X-Server-Group-Key")
    ] = None,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> JumpstatDetailPublic:
    group = await _get_server_group_from_api_key(
        session=session,
        x_server_group_key=x_server_group_key,
        authorization=authorization,
    )
    try:
        result = await ingest_jump_replay(
            session=session,
            group=group,
            replay_bytes=await replay.read(),
            source_name=replay.filename or "upload.replay",
        )
    except JumpReplayParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except JumpReplayIneligibleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    row = await crud.get_jumpstat_by_id(session=session, jumpstat_id=result.jumpstat.id)
    if row is None:
        raise HTTPException(status_code=500, detail="Jumpstat was not persisted")
    jumpstat, player, server_group = row
    return crud.to_jumpstat_detail_public(
        jumpstat=jumpstat,
        player=player,
        server_group=server_group,
    )


@router.post("/replay", response_model=JumpstatDetailPublic, status_code=201)
async def create_jumpstat_replay(
    *,
    session: SessionDep,
    request: Request,
    x_server_group_key: Annotated[
        str | None, Header(alias="X-Server-Group-Key")
    ] = None,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> JumpstatDetailPublic:
    group = await _get_server_group_from_api_key(
        session=session,
        x_server_group_key=x_server_group_key,
        authorization=authorization,
    )
    try:
        result = await ingest_jump_replay(
            session=session,
            group=group,
            replay_bytes=await request.body(),
            source_name="upload.replay",
        )
    except JumpReplayParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except JumpReplayIneligibleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    row = await crud.get_jumpstat_by_id(session=session, jumpstat_id=result.jumpstat.id)
    if row is None:
        raise HTTPException(status_code=500, detail="Jumpstat was not persisted")
    jumpstat, player, server_group = row
    return crud.to_jumpstat_detail_public(
        jumpstat=jumpstat,
        player=player,
        server_group=server_group,
    )


@router.get("", response_model=JumpstatsPublic)
async def read_jumpstats(
    session: SessionDep,
    query: Annotated[JumpstatListQuery, Query()],
) -> JumpstatsPublic:
    rows, count = await crud.read_jumpstats(session=session, query=query)
    return JumpstatsPublic(data=crud.to_jumpstat_publics(rows=rows), count=count)


@router.get("/replay-eligibility", response_model=JumpstatReplayEligibilityPublic)
async def read_jump_replay_eligibility(
    session: SessionDep,
    query: Annotated[JumpstatReplayEligibilityQuery, Query()],
) -> JumpstatReplayEligibilityPublic:
    jumped_at = query.jumped_at
    if jumped_at is None and query.jumped_at_unix is not None:
        jumped_at = datetime.fromtimestamp(query.jumped_at_unix, tz=UTC)
    return await get_jump_replay_eligibility(
        session=session,
        player_steamid64=query.player_steamid64,
        mode=query.mode,
        jump_type=query.type,
        distance=query.distance,
        jumped_at=jumped_at,
    )


@router.get("/{jumpstat_id}", response_model=JumpstatDetailPublic)
async def read_jumpstat(
    session: SessionDep,
    jumpstat_id: uuid.UUID,
) -> JumpstatDetailPublic:
    row = await crud.get_jumpstat_by_id(session=session, jumpstat_id=jumpstat_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Jumpstat not found")

    jumpstat, player, server_group = row
    return crud.to_jumpstat_detail_public(
        jumpstat=jumpstat,
        player=player,
        server_group=server_group,
    )


@router.get("/{jumpstat_id}/visualization", response_model=JumpstatVisualizationPublic)
async def read_jumpstat_visualization(
    session: SessionDep,
    jumpstat_id: uuid.UUID,
) -> JumpstatVisualizationPublic:
    jumpstat = await session.get(Jumpstat, jumpstat_id)
    if jumpstat is None:
        raise HTTPException(status_code=404, detail="Jumpstat not found")

    try:
        return await get_or_build_jumpstat_visualization(
            session=session,
            jumpstat=jumpstat,
        )
    except JumpstatVisualizationUnavailableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
