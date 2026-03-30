import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app import crud
from app.api.deps import SessionDep, get_current_active_superuser
from app.models import (
    Map,
    Mode,
    Player,
    Record,
    RecordListQuery,
    RecordPatch,
    RecordPublic,
    RecordsPublic,
    ServerGlobalapi,
    TeleportsType,
    User,
)

router = APIRouter(prefix="/records", tags=["records"])

CurrentSuperuser = Annotated[User, Depends(get_current_active_superuser)]


async def _to_record_public(session: SessionDep, record: Record) -> RecordPublic:
    player = await session.get(Player, record.steamid64)
    server = await session.get(ServerGlobalapi, record.server_id)
    map_obj = await session.get(Map, record.map_id)
    mode = await session.get(Mode, record.mode_id)
    if player is None or server is None or map_obj is None or mode is None:
        raise HTTPException(status_code=500, detail="Record relations are inconsistent")
    return crud.to_record_public(
        record=record,
        player=player,
        server=server,
        map_obj=map_obj,
        mode=mode,
    )


@router.get("/", response_model=RecordsPublic)
async def read_records(
    session: SessionDep,
    query: Annotated[RecordListQuery, Query()],
) -> Any:
    records, count = await crud.read_records(session=session, query=query)
    return RecordsPublic(
        data=[await _to_record_public(session, record) for record in records],
        count=count,
    )


@router.get("/pb", response_model=list[RecordPublic])
async def read_pb_records(
    session: SessionDep,
    mode_ids: Annotated[list[int], Query()],
    teleports_type: TeleportsType,
    map_id: Annotated[int | None, Query()] = None,
    stage: Annotated[int, Query(ge=0)] = 0,
    steamid64: Annotated[int | None, Query()] = None,
    server_ids: Annotated[list[int] | None, Query()] = None,
) -> Any:
    if not mode_ids:
        raise HTTPException(status_code=422, detail="mode_ids must not be empty")
    if (map_id is None) == (steamid64 is None):
        raise HTTPException(
            status_code=422,
            detail="Exactly one of map_id or steamid64 must be provided",
        )

    records = await crud.get_pb_records(
        session,
        map_id=map_id,
        stage=stage,
        steamid64=steamid64,
        mode_ids=mode_ids,
        teleports_type=teleports_type,
        server_ids=server_ids,
    )
    return [await _to_record_public(session, record) for record in records]


@router.get("/{record_uuid}", response_model=RecordPublic)
async def read_record(
    session: SessionDep,
    record_uuid: uuid.UUID,
) -> Any:
    record = await crud.get_record_by_uuid(session=session, record_uuid=record_uuid)
    if record is None:
        raise HTTPException(status_code=404, detail="Record not found")
    return await _to_record_public(session, record)


@router.patch(
    "/{record_uuid}",
    dependencies=[Depends(get_current_active_superuser)],
    response_model=RecordPublic,
)
async def patch_record(
    *,
    session: SessionDep,
    record_uuid: uuid.UUID,
    patch: RecordPatch,
    current_user: CurrentSuperuser,
) -> Any:
    del current_user
    record = await crud.get_record_by_uuid(session=session, record_uuid=record_uuid)
    if record is None:
        raise HTTPException(status_code=404, detail="Record not found")
    record = await crud.update_record_validity(session=session, record=record, patch=patch)
    return await _to_record_public(session, record)
