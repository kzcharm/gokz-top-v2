import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app import crud
from app.api.deps import SessionDep, get_current_active_superuser
from app.models import (
    Map,
    Mode,
    Player,
    RecentRecordListQuery,
    RecentRecordsPublic,
    Record,
    RecordListQuery,
    RecordPatch,
    RecordPublic,
    RecordScope,
    RecordsPublic,
    ServerGlobalapi,
    User,
)

router = APIRouter(prefix="/records", tags=["records"])

CurrentSuperuser = Annotated[User, Depends(get_current_active_superuser)]


async def _to_record_public(
    session: SessionDep,
    record: Record,
    *,
    points: int,
) -> RecordPublic:
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
        points=points,
    )


async def _to_record_publics(
    session: SessionDep,
    records: list[Record],
    *,
    scope: RecordScope,
) -> list[RecordPublic]:
    points_by_uuid = await crud.load_scoped_points_by_record_uuid(
        session=session,
        record_uuids=[record.uuid for record in records],
        scope=scope,
    )
    return [
        await _to_record_public(
            session,
            record,
            points=points_by_uuid.get(record.uuid, 0),
        )
        for record in records
    ]


@router.get("/", response_model=RecordsPublic)
async def read_records(
    session: SessionDep,
    query: Annotated[RecordListQuery, Query()],
) -> Any:
    records, count = await crud.read_records(session=session, query=query)
    return RecordsPublic(
        data=await _to_record_publics(session, records, scope=query.scope),
        count=count,
    )


@router.get("/recent", response_model=RecentRecordsPublic)
async def read_recent_records(
    session: SessionDep,
    query: Annotated[RecentRecordListQuery, Query()],
) -> Any:
    records, count = await crud.read_recent_records(session=session, query=query)
    return RecentRecordsPublic(data=records, count=count)


@router.get("/pb", response_model=list[RecordPublic])
async def read_pb_records(
    session: SessionDep,
    scope: RecordScope = RecordScope.OVR,
    is_pro_only: bool = False,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=10000)] = 100,
    map_id: Annotated[int | None, Query()] = None,
    stage: Annotated[int, Query(ge=0)] = 0,
    steamid64: Annotated[str | None, Query(pattern=r"^\d{17}$")] = None,
) -> Any:
    if (map_id is None) == (steamid64 is None):
        raise HTTPException(
            status_code=422,
            detail="Exactly one of map_id or steamid64 must be provided",
        )

    records = await crud.get_pb_records(
        session,
        map_id=map_id,
        stage=stage,
        steamid64=int(steamid64) if steamid64 is not None else None,
        scope=scope,
        is_pro_only=is_pro_only,
        offset=offset,
        limit=limit,
    )
    return await _to_record_publics(session, records, scope=scope)


@router.get("/{record_uuid}", response_model=RecordPublic)
async def read_record(
    session: SessionDep,
    record_uuid: uuid.UUID,
    scope: RecordScope = RecordScope.OVR,
) -> Any:
    record = await crud.get_record_by_uuid(session=session, record_uuid=record_uuid)
    if record is None:
        raise HTTPException(status_code=404, detail="Record not found")
    return (
        await _to_record_publics(session, [record], scope=scope)
    )[0]


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
    return (
        await _to_record_publics(session, [record], scope=RecordScope.OVR)
    )[0]
