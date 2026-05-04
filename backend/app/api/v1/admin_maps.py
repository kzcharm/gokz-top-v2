from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app import crud
from app.api.deps import SessionDep, get_current_active_map_admin
from app.models import (
    AdminMapListQuery,
    AdminMapPublic,
    AdminMapRecordFiltersPublic,
    AdminMapsPublic,
    AdminMapUpdate,
    AdminRecordFilterPublic,
    AdminRecordFilterTierUpdate,
    RecordFilter,
    User,
    get_datetime_utc,
)

router = APIRouter(prefix="/admin", tags=["admin-maps"])

CurrentMapAdmin = Annotated[User, Depends(get_current_active_map_admin)]


@router.get("/maps", response_model=AdminMapsPublic)
async def read_admin_maps(
    *,
    session: SessionDep,
    query: Annotated[AdminMapListQuery, Query()],
    _current_user: CurrentMapAdmin,
) -> AdminMapsPublic:
    maps, count = await crud.read_admin_maps(
        session=session,
        offset=query.offset,
        limit=query.limit,
        q=query.q,
        validated=query.validated,
    )
    return AdminMapsPublic(
        data=await crud.to_admin_map_publics(session=session, maps=maps),
        count=count,
    )


@router.patch("/maps/{id}", response_model=AdminMapPublic)
async def update_admin_map(
    *,
    session: SessionDep,
    id: int,
    map_in: AdminMapUpdate,
    current_user: CurrentMapAdmin,
) -> AdminMapPublic:
    map_obj = await crud.get_map_by_id(session=session, id=id)
    if map_obj is None:
        raise HTTPException(status_code=404, detail="Map not found")

    map_obj.validated = map_in.validated
    map_obj.approved_by_steamid64 = current_user.steamid64 if map_in.validated else 0
    map_obj.updated_at = get_datetime_utc()
    session.add(map_obj)
    await session.commit()
    await session.refresh(map_obj)

    return (
        await crud.to_admin_map_publics(
            session=session,
            maps=[map_obj],
        )
    )[0]


@router.get(
    "/maps/{id}/record-filters",
    response_model=AdminMapRecordFiltersPublic,
)
async def read_admin_map_record_filters(
    *,
    session: SessionDep,
    id: int,
    _current_user: CurrentMapAdmin,
) -> AdminMapRecordFiltersPublic:
    map_obj = await crud.get_map_by_id(session=session, id=id)
    if map_obj is None:
        raise HTTPException(status_code=404, detail="Map not found")
    return await crud.read_admin_map_record_filters(session=session, map_id=id)


@router.patch("/record-filters/{id}", response_model=AdminRecordFilterPublic)
async def update_admin_record_filter(
    *,
    session: SessionDep,
    id: int,
    filter_in: AdminRecordFilterTierUpdate,
    current_user: CurrentMapAdmin,
) -> AdminRecordFilterPublic:
    record_filter = await session.get(RecordFilter, id)
    if record_filter is None:
        raise HTTPException(status_code=404, detail="Record filter not found")
    if record_filter.map_id == -1:
        raise HTTPException(
            status_code=422,
            detail="Wildcard record filters cannot be edited from the maps admin",
        )
    if record_filter.tickrate != 128:
        raise HTTPException(
            status_code=422,
            detail="Only 128 tick record filters can be edited from the maps admin",
        )

    record_filter.tier = filter_in.tier
    record_filter.updated_at = get_datetime_utc()
    record_filter.updated_by_id = str(current_user.steamid64)
    session.add(record_filter)
    await session.commit()
    await session.refresh(record_filter)

    return crud.to_admin_record_filter_public(record_filter=record_filter)
