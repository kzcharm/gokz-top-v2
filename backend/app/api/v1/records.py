import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from app import crud
from app.api.deps import SessionDep, get_current_active_admin
from app.core.regions import is_valid_region_code
from app.crud import player as player_crud
from app.crud.record import get_pb_record_publics
from app.models import (
    Map,
    ModeScope,
    Player,
    RecentRecordListQuery,
    RecentRecordsPublic,
    Record,
    RecordBulkDeleteCourse,
    RecordBulkDeleteResult,
    RecordListQuery,
    RecordPatch,
    RecordPbBucketRebuildResult,
    RecordPbSortBy,
    RecordPublic,
    RecordRankPublic,
    RecordRanksPublic,
    RecordsPublic,
    RecordType,
    ServerGlobalapi,
    ServerGroup,
    User,
)

router = APIRouter(prefix="/records", tags=["records"])

CurrentAdmin = Annotated[User, Depends(get_current_active_admin)]


async def _resolve_player_identifier_to_steamid64_or_404(
    *, session: SessionDep, identifier: str
) -> int:
    steamid64 = await player_crud.resolve_player_identifier_to_steamid64(
        session=session,
        identifier=identifier,
    )
    if steamid64 is None:
        raise HTTPException(status_code=404, detail="Player not found")
    return steamid64


def _validate_geography_filters(*, country: str | None, region: str | None) -> None:
    if country is not None and region is not None:
        raise HTTPException(
            status_code=422,
            detail="country and region filters are mutually exclusive. Please provide only one.",
        )
    if region is not None and not is_valid_region_code(region):
        raise HTTPException(status_code=422, detail="Invalid region")


async def _to_record_public(
    session: SessionDep,
    record: Record,
    *,
    map_tier: int,
    points: int,
) -> RecordPublic:
    player = await session.get(Player, record.steamid64)
    server = await session.get(ServerGlobalapi, record.server_id)
    map_obj = await session.get(Map, record.map_id)
    mode = await crud.get_mode_by_short_name(session=session, short_name=record.mode)
    if player is None or server is None or map_obj is None or mode is None:
        raise HTTPException(status_code=500, detail="Record relations are inconsistent")
    server_group = (
        await session.get(ServerGroup, server.group_id)
        if server.group_id is not None
        else None
    )
    return crud.to_record_public(
        record=record,
        player=player,
        server=server,
        server_group=server_group,
        map_obj=map_obj,
        mode=mode,
        map_tier=map_tier,
        points=points,
    )


async def _to_record_publics(
    session: SessionDep,
    records: list[Record],
    *,
    scope: ModeScope,
) -> list[RecordPublic]:
    points_by_uuid = await crud.load_scoped_points_by_record_uuid(
        session=session,
        record_uuids=[record.uuid for record in records],
        scope=scope,
    )
    tiers_by_course = await crud.load_scoped_course_tiers(
        session=session,
        course_keys=[(record.map_id, record.stage) for record in records],
        scope=scope,
    )
    return [
        await _to_record_public(
            session,
            record,
            map_tier=tiers_by_course[(record.map_id, record.stage)],
            points=points_by_uuid.get(record.uuid, 0),
        )
        for record in records
    ]


@router.get("", response_model=RecordsPublic)
async def read_records(
    session: SessionDep,
    query: Annotated[RecordListQuery, Query()],
) -> Any:
    if query.map_id is not None and query.map_name is not None:
        raise HTTPException(
            status_code=422,
            detail="map_id and map_name filters are mutually exclusive. Please provide only one.",
        )
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
    scope: ModeScope = ModeScope.OVR,
    type: RecordType = RecordType.NUB,
    exclude_cheaters: bool = True,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=10000)] = 100,
    map_id: Annotated[int | None, Query()] = None,
    map_name: Annotated[str | None, Query()] = None,
    stage: Annotated[int, Query(ge=0)] = 0,
    identifier: Annotated[str | None, Query()] = None,
    country: Annotated[str | None, Query(max_length=2)] = None,
    region: Annotated[str | None, Query(max_length=3)] = None,
    sort_by: Annotated[RecordPbSortBy, Query()] = "time",
    sort_order: Annotated[Literal["asc", "desc"] | None, Query()] = None,
) -> Any:
    if map_id is not None and map_name is not None:
        raise HTTPException(
            status_code=422,
            detail="map_id and map_name filters are mutually exclusive. Please provide only one.",
        )
    has_map_anchor = map_id is not None or map_name is not None
    has_player_anchor = identifier is not None
    if not has_map_anchor and not has_player_anchor:
        raise HTTPException(
            status_code=422,
            detail="At least one of map_id/map_name or identifier must be provided",
        )
    normalized_country = country.strip().upper() if country is not None and country.strip() else None
    normalized_region = region.strip().upper() if region is not None and region.strip() else None
    _validate_geography_filters(country=normalized_country, region=normalized_region)

    return await get_pb_record_publics(
        session,
        map_id=map_id,
        map_name=map_name,
        stage=stage,
        steamid64=(
            await _resolve_player_identifier_to_steamid64_or_404(
                session=session,
                identifier=identifier,
            )
            if identifier is not None
            else None
        ),
        scope=scope,
        record_type=type,
        country=normalized_country,
        region=normalized_region,
        sort_by=sort_by,
        sort_order=sort_order,
        exclude_cheaters=exclude_cheaters,
        offset=offset,
        limit=limit,
    )


@router.get("/rank", response_model=RecordRanksPublic)
async def read_record_ranks(
    session: SessionDep,
    record_uuids: Annotated[list[uuid.UUID], Query(alias="uuid_list")],
    scope: ModeScope = ModeScope.OVR,
    type: RecordType = RecordType.NUB,
    country: Annotated[str | None, Query(max_length=2)] = None,
) -> RecordRanksPublic:
    normalized_country = country.strip().upper() if country is not None and country.strip() else None
    ranks = await crud.read_record_ranks(
        session=session,
        record_uuids=record_uuids,
        scope=scope,
        record_type=type,
        country=normalized_country,
    )
    return RecordRanksPublic(
        data=[
            RecordRankPublic(
                record_uuid=record_uuid,
                rank=rank,
                total_count=total_count,
            )
            for record_uuid, rank, total_count in ranks
        ],
        count=len(ranks),
    )


@router.get("/{record_uuid}", response_model=RecordPublic)
async def read_record(
    session: SessionDep,
    record_uuid: uuid.UUID,
    scope: ModeScope = ModeScope.OVR,
) -> Any:
    record = await crud.get_record_by_uuid(session=session, record_uuid=record_uuid)
    if record is None:
        raise HTTPException(status_code=404, detail="Record not found")
    return (
        await _to_record_publics(session, [record], scope=scope)
    )[0]


@router.patch(
    "/{record_uuid}",
    dependencies=[Depends(get_current_active_admin)],
    response_model=RecordPublic,
)
async def patch_record(
    *,
    session: SessionDep,
    record_uuid: uuid.UUID,
    patch: RecordPatch,
    current_user: CurrentAdmin,
) -> Any:
    record = await crud.get_record_by_uuid(session=session, record_uuid=record_uuid)
    if record is None:
        raise HTTPException(status_code=404, detail="Record not found")
    record = await crud.update_record_validity(
        session=session,
        record=record,
        patch=patch,
        actor_steamid64=current_user.steamid64,
    )
    return (
        await _to_record_publics(session, [record], scope=ModeScope.OVR)
    )[0]


@router.post(
    "/bulk-delete-course",
    dependencies=[Depends(get_current_active_admin)],
    response_model=RecordBulkDeleteResult,
)
async def bulk_delete_course_records(
    *,
    session: SessionDep,
    payload: RecordBulkDeleteCourse,
    current_user: CurrentAdmin,
) -> RecordBulkDeleteResult:
    records = await crud.bulk_soft_delete_course_records(
        session=session,
        payload=payload,
        actor_steamid64=current_user.steamid64,
    )
    return RecordBulkDeleteResult(
        data=await _to_record_publics(session, records, scope=ModeScope.OVR),
        count=len(records),
    )


@router.post(
    "/rebuild-pb-points-bucket",
    dependencies=[Depends(get_current_active_admin)],
    response_model=RecordPbBucketRebuildResult,
)
async def rebuild_pb_points_bucket(
    *,
    session: SessionDep,
    map_id: int,
    stage: int = 0,
    scope: ModeScope = ModeScope.OVR,
    type: RecordType = RecordType.NUB,
    _current_user: CurrentAdmin,
) -> RecordPbBucketRebuildResult:
    course = await crud.get_map_course_by_map_stage(
        session=session,
        map_id=map_id,
        stage=stage,
    )
    if course is None or course.id is None:
        raise HTTPException(status_code=404, detail="Map course not found")

    updated_count = await crud.rebuild_record_pb_points_bucket(
        session=session,
        course_id=course.id,
        scope_id=scope.scope_id,
        record_type=type,
    )
    await session.commit()
    return RecordPbBucketRebuildResult(
        course_id=course.id,
        scope=scope,
        type=type,
        updated_count=updated_count,
    )
