import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from app import crud
from app.api.deps import SessionDep
from app.models import Jumpstat, Map, Record, RecordsPublic, ReplayListQuery
from app.services.jump_replay_storage import get_jump_replay_path
from app.services.run_replay_listing import list_run_replay_record_uuids
from app.services.run_replay_storage import get_run_replay_path

router = APIRouter(prefix="/replays", tags=["replays"])


def _build_replay_file_response(*, path: Path, filename: str) -> FileResponse:
    return FileResponse(
        path=path,
        media_type="application/octet-stream",
        filename=filename,
    )


@router.get("", response_model=RecordsPublic)
async def read_replays(
    session: SessionDep,
    query: Annotated[ReplayListQuery, Query()],
) -> RecordsPublic:
    try:
        record_uuids = list_run_replay_record_uuids(query=query)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    record_publics = await crud.read_records_with_replays(
        session=session,
        record_uuids=record_uuids,
        scope=query.scope,
        exclude_cheaters=query.exclude_cheaters,
    )
    count = len(record_publics)
    return RecordsPublic(
        data=record_publics[query.offset : query.offset + query.limit],
        count=count,
    )


@router.get("/jump/{jumpstat_id}")
async def read_jump_replay(
    session: SessionDep,
    jumpstat_id: uuid.UUID,
) -> FileResponse:
    jumpstat = await session.get(Jumpstat, jumpstat_id)
    if jumpstat is None:
        raise HTTPException(status_code=404, detail="Jumpstat not found")

    replay_path = get_jump_replay_path(jumpstat_id=jumpstat.id)
    if not replay_path.is_file():
        raise HTTPException(status_code=404, detail="Jump replay not found")

    return _build_replay_file_response(
        path=replay_path,
        filename=f"{jumpstat.id}.replay",
    )


@router.get("/{record_uuid}")
async def read_run_replay(
    session: SessionDep,
    record_uuid: uuid.UUID,
) -> FileResponse:
    record = await session.get(Record, record_uuid)
    if record is None:
        raise HTTPException(status_code=404, detail="Record not found")

    map_obj = await session.get(Map, record.map_id)
    if map_obj is None:
        raise HTTPException(status_code=500, detail="Record relations are inconsistent")

    replay_path = get_run_replay_path(map_name=map_obj.name, replay_id=record.uuid)
    if not replay_path.is_file():
        raise HTTPException(status_code=404, detail="Replay not found")

    return _build_replay_file_response(
        path=replay_path,
        filename=f"{record.uuid}.replay",
    )
