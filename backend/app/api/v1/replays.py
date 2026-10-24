import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel

from app import crud
from app.api.deps import SessionDep
from app.models import Jumpstat, RecordReplay, RecordsPublic, ReplayListQuery
from app.services import r2_storage
from app.services.jump_replay_storage import get_jump_replay_path
from app.services.record_replay_catalog import list_replays

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
    record_uuids, count = await list_replays(session, query)
    record_publics = await crud.read_records_with_replays(
        session=session,
        record_uuids=record_uuids,
        scope=query.scope,
        exclude_cheaters=query.exclude_cheaters,
    )
    return RecordsPublic(
        data=record_publics,
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


class ReplayDownloadUrl(BaseModel):
    url: str


@router.get("/{record_uuid}/url", response_model=ReplayDownloadUrl)
async def read_run_replay_url(
    session: SessionDep, request: Request, record_uuid: uuid.UUID
) -> ReplayDownloadUrl:
    """Resolve public storage directly to avoid CORS-tainted cross-origin redirects."""
    record = await crud.get_record_by_uuid(session=session, record_uuid=record_uuid)
    if record is None:
        raise HTTPException(status_code=404, detail="Record not found")
    replay = await session.get(RecordReplay, record.uuid)
    if replay is None or not replay.available:
        raise HTTPException(status_code=404, detail="Replay not found")
    return ReplayDownloadUrl(
        url=(
            r2_storage.build_public_url(replay.key)
            if replay.storage == "r2"
            else str(request.url_for("read_run_replay", record_uuid=record.uuid))
        )
    )


@router.get("/{record_uuid}", response_model=None)
async def read_run_replay(
    session: SessionDep,
    record_uuid: uuid.UUID,
) -> FileResponse | RedirectResponse:
    record = await crud.get_record_by_uuid(session=session, record_uuid=record_uuid)
    if record is None:
        raise HTTPException(status_code=404, detail="Record not found")
    replay = await session.get(RecordReplay, record.uuid)
    if replay is None or not replay.available:
        raise HTTPException(status_code=404, detail="Replay not found")
    if replay.storage == "r2":
        return RedirectResponse(
            r2_storage.build_public_url(replay.key), status_code=307
        )
    return _build_replay_file_response(
        path=Path(replay.key), filename=f"{record.uuid}.replay"
    )
