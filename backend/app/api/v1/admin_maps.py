from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app import crud
from app.api.deps import SessionDep, get_current_active_map_admin
from app.models import (
    AdminCourseTierPublic,
    AdminCourseTierUpdate,
    AdminMapCourseTiersPublic,
    AdminMapListQuery,
    AdminMapPublic,
    AdminMapRecordFiltersPublic,
    AdminMapsPublic,
    AdminMapUpdate,
    KZMode,
    MapCourse,
    MapCourseTier,
    User,
    get_datetime_utc,
)
from app.services.map_authors import (
    ensure_author_players_exist,
    normalize_author_fields,
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
    if map_in.authors is not None or map_in.no_steamid_names is not None:
        map_obj.authors, map_obj.no_steamid_names = normalize_author_fields(
            authors=map_in.authors if map_in.authors is not None else map_obj.authors,
            no_steamid_names=(
                map_in.no_steamid_names
                if map_in.no_steamid_names is not None
                else map_obj.no_steamid_names
            ),
        )
        await ensure_author_players_exist(
            session=session,
            author_steamid64s=map_obj.authors or [],
        )
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
    "/maps/{id}/course-tiers",
    response_model=AdminMapCourseTiersPublic,
)
async def read_admin_map_course_tiers(
    *,
    session: SessionDep,
    id: int,
    _current_user: CurrentMapAdmin,
) -> AdminMapCourseTiersPublic:
    map_obj = await crud.get_map_by_id(session=session, id=id)
    if map_obj is None:
        raise HTTPException(status_code=404, detail="Map not found")
    return await crud.read_admin_map_course_tiers(session=session, map_id=id)


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


@router.patch("/course-tiers/{course_id}/{mode}", response_model=AdminCourseTierPublic)
async def update_admin_course_tier(
    *,
    session: SessionDep,
    course_id: int,
    mode: KZMode,
    tier_in: AdminCourseTierUpdate,
    current_user: CurrentMapAdmin,
) -> AdminCourseTierPublic:
    course = await session.get(MapCourse, course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Map course not found")

    course_tier = await session.get(MapCourseTier, (course_id, mode))
    now = get_datetime_utc()
    if course_tier is None:
        course_tier = MapCourseTier(
            course_id=course_id,
            mode=mode,
            tier=tier_in.tier,
            created_on=now,
            updated_on=now,
            updated_by_id=str(current_user.steamid64),
        )
    else:
        course_tier.tier = tier_in.tier
        course_tier.updated_at = now
        course_tier.updated_by_id = str(current_user.steamid64)

    session.add(course_tier)
    await session.commit()
    await session.refresh(course_tier)

    return crud.to_admin_course_tier_public(
        course=course,
        mode=mode,
        course_tier=course_tier,
    )
