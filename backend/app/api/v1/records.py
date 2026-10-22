import hashlib
import json
import uuid
from collections.abc import Sequence
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import true
from sqlmodel import col, select
from sqlmodel.sql.expression import SelectOfScalar

from app import crud
from app.api.deps import OptionalCurrentUser, SessionDep, get_current_active_admin
from app.core.regions import is_valid_region_code
from app.crud import player as player_crud
from app.crud import record as record_crud
from app.crud.recent_wr import (
    read_recent_wrs as read_recent_wrs_from_cache,
)
from app.crud.recent_wr import (
    recent_wr_backfill_is_ready,
)
from app.crud.record import get_pb_record_publics, soft_delete_records_with_audit
from app.models import (
    Map,
    ModeScope,
    Player,
    ReactionSummaryPublic,
    ReactionTargetType,
    RecentRecordListQuery,
    RecentRecordsPublic,
    RecentWrListQuery,
    RecentWrsPublic,
    Record,
    RecordBulkDeleteCourse,
    RecordBulkDeleteFaster,
    RecordBulkDeleteFasterPreview,
    RecordBulkDeleteFasterPreviewPlayer,
    RecordBulkDeleteFasterPreviewRun,
    RecordBulkDeleteFasterResult,
    RecordBulkDeleteResult,
    RecordListQuery,
    RecordModerationAction,
    RecordModerationActionType,
    RecordPatch,
    RecordPbBucketRebuildResult,
    RecordPbSortBy,
    RecordPublic,
    RecordRankPublic,
    RecordRanksPublic,
    RecordRunHistoryPublic,
    RecordsPublic,
    RecordType,
    ServerGlobalapi,
    ServerGroup,
    User,
    mode_scope_modes,
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


@router.get("/wrs/recent", response_model=RecentWrsPublic)
async def read_recent_wrs(
    session: SessionDep,
    current_user: OptionalCurrentUser,
    query: Annotated[RecentWrListQuery, Query()],
) -> RecentWrsPublic:
    if not await recent_wr_backfill_is_ready(session=session):
        raise HTTPException(
            status_code=503,
            detail="Recent WR history is being prepared.",
        )
    records, count = await read_recent_wrs_from_cache(session=session, query=query)
    summaries = await crud.load_reaction_summaries(
        session=session,
        target_type=ReactionTargetType.RECENT_WR,
        target_ids=[item.record.uuid for item in records],
        viewer_steamid64=current_user.steamid64 if current_user else None,
    )
    for item in records:
        item.reactions = summaries.get(item.record.uuid, ReactionSummaryPublic())
    return RecentWrsPublic(data=records, count=count)


@router.get("/pb", response_model=list[RecordPublic])
async def read_pb_records(
    session: SessionDep,
    include_ranks: Annotated[
        bool,
        Query(
            description="Include live competitive ranks for the selected scope, type, and geography; return at most 50 PBs."
        ),
    ] = False,
    scope: ModeScope = ModeScope.OVR,
    type: RecordType = RecordType.NUB,
    exclude_cheaters: bool = True,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=10000)] = 100,
    map_id: Annotated[int | None, Query()] = None,
    map_name: Annotated[str | None, Query()] = None,
    stage: Annotated[int, Query(ge=0)] = 0,
    is_bonus: bool = False,
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
    normalized_country = (
        country.strip().upper() if country is not None and country.strip() else None
    )
    normalized_region = (
        region.strip().upper() if region is not None and region.strip() else None
    )
    _validate_geography_filters(country=normalized_country, region=normalized_region)

    return await get_pb_record_publics(
        session,
        include_ranks=include_ranks,
        map_id=map_id,
        map_name=map_name,
        stage=stage,
        is_bonus=is_bonus,
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
        limit=min(limit, 50) if include_ranks else limit,
    )


@router.get("/pb/ranks", response_model=dict[uuid.UUID, int | None])
async def read_pb_page_ranks(
    session: SessionDep,
    record_uuids: Annotated[
        list[uuid.UUID], Query(alias="uuid_list", min_length=1, max_length=50)
    ],
    scope: ModeScope = ModeScope.OVR,
    type: RecordType = RecordType.NUB,
    country: Annotated[str | None, Query(max_length=2)] = None,
    region: Annotated[str | None, Query(max_length=3)] = None,
) -> dict[uuid.UUID, int | None]:
    """Return competitive ranks for at most 50 visible PBs, without totals."""
    normalized_country = (
        country.strip().upper() if country and country.strip() else None
    )
    normalized_region = region.strip().upper() if region and region.strip() else None
    _validate_geography_filters(country=normalized_country, region=normalized_region)
    ranks = await record_crud.read_pb_ranks(
        session=session,
        record_uuids=record_uuids,
        scope=scope,
        record_type=type,
        country=normalized_country,
        region=normalized_region,
    )
    return {record_uuid: ranks.get(record_uuid) for record_uuid in record_uuids}


@router.get("/rank", response_model=RecordRanksPublic)
async def read_record_ranks(
    session: SessionDep,
    record_uuids: Annotated[list[uuid.UUID], Query(alias="uuid_list")],
    scope: ModeScope = ModeScope.OVR,
    type: RecordType = RecordType.NUB,
    country: Annotated[str | None, Query(max_length=2)] = None,
) -> RecordRanksPublic:
    normalized_country = (
        country.strip().upper() if country is not None and country.strip() else None
    )
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


@router.get("/run-history", response_model=RecordRunHistoryPublic)
async def read_record_run_history(
    session: SessionDep,
    identifier: Annotated[str, Query()],
    map_id: Annotated[int, Query()],
    stage: Annotated[int, Query(ge=0)] = 0,
    scope: ModeScope = ModeScope.OVR,
    type: RecordType = RecordType.NUB,
    exclude_cheaters: bool = True,
) -> RecordRunHistoryPublic:
    steamid64 = await _resolve_player_identifier_to_steamid64_or_404(
        session=session,
        identifier=identifier,
    )
    return await crud.read_record_run_history(
        session=session,
        steamid64=steamid64,
        map_id=map_id,
        stage=stage,
        scope=scope,
        record_type=type,
        exclude_cheaters=exclude_cheaters,
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
    return (await _to_record_publics(session, [record], scope=scope))[0]


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
    return (await _to_record_publics(session, [record], scope=ModeScope.OVR))[0]


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


async def _faster_records_selection(
    *,
    session: SessionDep,
    payload: RecordBulkDeleteFaster,
) -> tuple[Record, SelectOfScalar[Record]]:
    reference = await session.get(Record, payload.record_uuid)
    if reference is None:
        raise HTTPException(status_code=404, detail="Record not found")
    if not reference.is_valid:
        raise HTTPException(
            status_code=409, detail="The selected record is already invalid"
        )
    modes = mode_scope_modes(payload.scope)
    if reference.mode not in modes or (
        payload.type == RecordType.PRO and reference.teleports != 0
    ):
        raise HTTPException(
            status_code=422,
            detail="Record does not match the selected scope and category",
        )
    statement = select(Record).where(
        col(Record.map_id) == reference.map_id,
        col(Record.stage) == reference.stage,
        col(Record.mode).in_(modes),
        # Match the existing partial-index predicate. PostgreSQL does not
        # infer `is_valid = true` from `is_valid IS TRUE` for these indexes.
        col(Record.is_valid) == true(),
        col(Record.time) < reference.time,
    )
    if payload.type == RecordType.PRO:
        statement = statement.where(col(Record.teleports) == 0)
    return reference, statement


def _faster_records_preview_token(
    *,
    reference: Record,
    payload: RecordBulkDeleteFaster,
    records: Sequence[Record],
) -> str:
    snapshot = {
        "reference": reference.model_dump(mode="json"),
        "scope": payload.scope.value,
        "type": payload.type.value,
        "records": [
            record.model_dump(mode="json")
            for record in sorted(records, key=lambda r: str(r.uuid))
        ],
    }
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()


@router.post(
    "/bulk-delete-faster/preview", response_model=RecordBulkDeleteFasterPreview
)
async def preview_bulk_delete_faster_records(
    *,
    session: SessionDep,
    payload: RecordBulkDeleteFaster,
    _current_user: CurrentAdmin,
) -> RecordBulkDeleteFasterPreview:
    reference, selection = await _faster_records_selection(
        session=session, payload=payload
    )
    where_clause = selection.whereclause
    assert where_clause is not None
    rows = (
        await session.exec(
            select(Record, Player, ServerGlobalapi)
            .join(Player, col(Player.steamid64) == col(Record.steamid64))
            .join(ServerGlobalapi, col(ServerGlobalapi.id) == col(Record.server_id))
            .where(where_clause)
            .order_by(col(Record.time), col(Record.uuid))
        )
    ).all()
    players: dict[int, RecordBulkDeleteFasterPreviewPlayer] = {}
    for record, player, server in rows:
        group = players.get(player.steamid64)
        if group is None:
            group = RecordBulkDeleteFasterPreviewPlayer(
                player=player_crud.to_player_ref_public(player=player),
                records=[],
            )
            players[player.steamid64] = group
        group.records.append(
            RecordBulkDeleteFasterPreviewRun(
                uuid=record.uuid,
                time=float(record.time),
                mode=record.mode,
                teleports=record.teleports,
                server_name=server.name or "",
                created_on=record.created_at,
            )
        )
    return RecordBulkDeleteFasterPreview(
        count=len(rows),
        players=list(players.values()),
        preview_token=_faster_records_preview_token(
            reference=reference, payload=payload, records=[row[0] for row in rows]
        ),
    )


@router.post("/bulk-delete-faster", response_model=RecordBulkDeleteFasterResult)
async def bulk_delete_faster_records(
    *,
    session: SessionDep,
    payload: RecordBulkDeleteFaster,
    current_user: CurrentAdmin,
) -> RecordBulkDeleteFasterResult:
    reference, statement = await _faster_records_selection(
        session=session, payload=payload
    )
    records = list(
        (
            await session.exec(statement.order_by(col(Record.uuid)).with_for_update())
        ).all()
    )
    if (
        payload.preview_token is not None
        and payload.preview_token
        != _faster_records_preview_token(
            reference=reference,
            payload=payload,
            records=records,
        )
    ):
        raise HTTPException(
            status_code=409,
            detail="Records have changed. Refresh the preview before deleting.",
        )
    await soft_delete_records_with_audit(
        session=session,
        records=records,
        action=RecordModerationAction(
            actor_steamid64=current_user.steamid64,
            action_type=RecordModerationActionType.BULK_SOFT_DELETE_FASTER,
            target_record_uuid=reference.uuid,
            target_map_id=reference.map_id,
            target_stage=reference.stage,
        ),
    )
    return RecordBulkDeleteFasterResult(count=len(records))


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
