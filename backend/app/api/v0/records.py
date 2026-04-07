from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query

from app import crud
from app.api.deps import SessionDep
from app.models import (
    CANONICAL_MODE_SEEDS,
    Map,
    Mode,
    Player,
    RecentRecordCompatPublicV0,
    Record,
    RecordCompatPublicV0,
    ServerGlobalapi,
    WorldRecordCountCompatPublicV0,
)

router = APIRouter(prefix="/records", tags=["records"])

_MODE_LOOKUP = {
    seed.name.lower(): seed.id for seed in CANONICAL_MODE_SEEDS
} | {seed.name_short.lower(): seed.id for seed in CANONICAL_MODE_SEEDS}
_MODE_LOOKUP |= {str(seed.id): seed.id for seed in CANONICAL_MODE_SEEDS}


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.year >= 1900 else None
    except ValueError:
        return None


def _resolve_mode_ids(
    *,
    modes_list: list[str] | None,
    modes_list_string: str | None,
) -> list[int]:
    raw_values: list[str] = []
    if modes_list_string:
        raw_values.extend(
            token.strip() for token in modes_list_string.split(",") if token.strip()
        )
    if modes_list:
        raw_values.extend(token.strip() for token in modes_list if token.strip())
    if not raw_values:
        return [seed.id for seed in CANONICAL_MODE_SEEDS]

    resolved: list[int] = []
    for raw in raw_values:
        normalized = raw.lower()
        if normalized in _MODE_LOOKUP:
            resolved.append(_MODE_LOOKUP[normalized])
    return sorted(set(resolved))


async def _to_record_compat_public_v0(
    session: SessionDep,
    record: Record,
) -> RecordCompatPublicV0:
    player = await session.get(Player, record.steamid64)
    server = await session.get(ServerGlobalapi, record.server_id)
    map_obj = await session.get(Map, record.map_id)
    mode = await session.get(Mode, record.mode_id)
    if player is None or server is None or map_obj is None or mode is None:
        raise HTTPException(status_code=500, detail="Record relations are inconsistent")
    return crud.to_record_compat_public_v0(
        record=record,
        player=player,
        server=server,
        map_obj=map_obj,
        mode=mode,
    )


@router.get("/{id:int}", response_model=RecordCompatPublicV0)
async def read_record_by_id(session: SessionDep, id: int) -> Any:
    record = await crud.get_record_by_id(session=session, record_id=id)
    if record is None or record.id is None:
        raise HTTPException(status_code=404, detail="Record not found")
    return await _to_record_compat_public_v0(session, record)


@router.get("/place/{id:int}", response_model=int)
async def read_record_place(session: SessionDep, id: int) -> Any:
    record = await crud.get_record_by_id(session=session, record_id=id)
    if record is None or record.id is None:
        raise HTTPException(status_code=404, detail="Record not found")
    return await crud.get_record_place(session=session, record=record)


@router.get("/top", response_model=list[RecordCompatPublicV0])
async def read_top_records(
    session: SessionDep,
    steamid64: Annotated[int | None, Query()] = None,
    server_id: Annotated[int | None, Query()] = None,
    map_id: Annotated[int | None, Query()] = None,
    map_name: Annotated[str | None, Query()] = None,
    stage: Annotated[int, Query(ge=0)] = 0,
    modes_list_string: Annotated[str | None, Query()] = None,
    modes_list: Annotated[list[str] | None, Query()] = None,
    has_teleports: Annotated[bool | None, Query()] = None,
    player_name: Annotated[str | None, Query()] = None,
    exclude_cheaters: Annotated[bool, Query()] = True,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=10000)] = 100,
    tickrate: Annotated[int | None, Query()] = None,
) -> Any:
    if tickrate is not None and tickrate != 128:
        return []

    mode_ids = _resolve_mode_ids(
        modes_list=modes_list,
        modes_list_string=modes_list_string,
    )
    records = await crud.get_top_records_v0(
        session=session,
        steamid64=steamid64,
        server_id=server_id,
        map_id=map_id,
        map_name=map_name,
        mode_ids=mode_ids,
        stage=stage,
        has_teleports=has_teleports,
        player_name=player_name,
        exclude_cheaters=exclude_cheaters,
        offset=offset,
        limit=limit,
    )
    return [await _to_record_compat_public_v0(session, record) for record in records]


@router.get(
    "/top/world_records",
    response_model=list[WorldRecordCountCompatPublicV0],
)
async def read_world_record_counts(
    session: SessionDep,
    ids: Annotated[list[int] | None, Query()] = None,
    map_ids: Annotated[list[int] | None, Query()] = None,
    stages: Annotated[list[int] | None, Query()] = None,
    mode_ids: Annotated[list[int] | None, Query()] = None,
    tickrates: Annotated[list[int] | None, Query()] = None,
    has_teleports: Annotated[bool | None, Query()] = None,
    exclude_cheaters: Annotated[bool, Query()] = True,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=10000)] = 100,
) -> Any:
    if tickrates and any(tickrate != 128 for tickrate in tickrates):
        return []
    return await crud.get_world_record_counts_v0(
        session=session,
        ids=ids,
        map_ids=map_ids,
        stages=stages,
        mode_ids=mode_ids,
        has_teleports=has_teleports,
        exclude_cheaters=exclude_cheaters,
        offset=offset,
        limit=limit,
    )


@router.get("/top/recent", response_model=list[RecentRecordCompatPublicV0])
async def read_recent_top_records(
    session: SessionDep,
    steamid64: Annotated[int | None, Query()] = None,
    map_id: Annotated[int | None, Query()] = None,
    map_name: Annotated[str | None, Query()] = None,
    has_teleports: Annotated[bool | None, Query()] = None,
    tickrate: Annotated[int | None, Query()] = None,
    stage: Annotated[int | None, Query(ge=0)] = None,
    modes_list_string: Annotated[str | None, Query()] = None,
    modes_list: Annotated[list[str] | None, Query()] = None,
    place_top_at_least: Annotated[int | None, Query(ge=1)] = None,
    place_top_overall_at_least: Annotated[int | None, Query(ge=1)] = None,
    created_since: Annotated[str | None, Query()] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=10000)] = 100,
) -> Any:
    if tickrate is not None and tickrate != 128:
        return []
    mode_ids = _resolve_mode_ids(
        modes_list=modes_list,
        modes_list_string=modes_list_string,
    )
    return await crud.get_recent_top_records_v0(
        session=session,
        steamid64=steamid64,
        map_id=map_id,
        map_name=map_name,
        mode_ids=mode_ids,
        stage=stage,
        has_teleports=has_teleports,
        created_since=_parse_datetime(created_since),
        place_top_at_least=place_top_at_least,
        place_top_overall_at_least=place_top_overall_at_least,
        offset=offset,
        limit=limit,
    )


@router.get("/record_filter")
async def read_record_filter_placeholder() -> Any:
    return {"message": "record_filter endpoint not implemented"}
