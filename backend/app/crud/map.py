from datetime import datetime

from sqlalchemy import func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import (
    AdminMapPublic,
    Map,
    MapCompatPublicV0,
    MapCourse,
    MapCourseTier,
    MapFileDistribution,
    MapPublic,
    MapReviewSummaryPublic,
    MapTiers,
    ModeScope,
    mode_scope_modes,
)

from .map_review import load_map_review_summaries
from .record_filter import load_map_tiers_by_scope


def _build_read_maps_statement(
    *,
    id: list[int] | None = None,
    name: str | None = None,
    larger_than_filesize: int | None = None,
    smaller_than_filesize: int | None = None,
    is_validated: bool | None = None,
    difficulty: int | None = None,
    scope: ModeScope | None = None,
    created_since: datetime | None = None,
    updated_since: datetime | None = None,
):
    statement = select(Map)

    if id:
        statement = statement.where(Map.id.in_(id))
    if name:
        statement = statement.where(Map.name == name)
    if larger_than_filesize is not None:
        statement = statement.where(Map.filesize > larger_than_filesize)
    if smaller_than_filesize is not None:
        statement = statement.where(Map.filesize < smaller_than_filesize)
    if is_validated is not None:
        statement = statement.where(Map.validated == is_validated)
    if difficulty is not None:
        statement = statement.where(Map.difficulty == difficulty)
    if scope is not None:
        scoped_map_ids = (
            select(col(MapCourse.map_id))
            .join(MapCourseTier, col(MapCourseTier.course_id) == col(MapCourse.id))
            .where(
                col(MapCourse.stage) == 0,
                col(MapCourseTier.mode).in_(list(mode_scope_modes(scope))),
                col(MapCourseTier.tier) > 0,
            )
        )
        statement = statement.where(col(Map.id).in_(scoped_map_ids))
    if created_since is not None:
        statement = statement.where(Map.created_at >= created_since)
    if updated_since is not None:
        statement = statement.where(Map.updated_at >= updated_since)

    if is_validated is None:
        return statement.order_by(col(Map.validated).desc(), col(Map.name).asc())
    return statement.order_by(col(Map.name).asc())


async def read_maps(
    *,
    session: AsyncSession,
    offset: int = 0,
    limit: int = 100,
    id: list[int] | None = None,
    name: str | None = None,
    larger_than_filesize: int | None = None,
    smaller_than_filesize: int | None = None,
    is_validated: bool | None = None,
    difficulty: int | None = None,
    scope: ModeScope | None = None,
    created_since: datetime | None = None,
    updated_since: datetime | None = None,
) -> list[Map]:
    statement = _build_read_maps_statement(
        id=id,
        name=name,
        larger_than_filesize=larger_than_filesize,
        smaller_than_filesize=smaller_than_filesize,
        is_validated=is_validated,
        difficulty=difficulty,
        scope=scope,
        created_since=created_since,
        updated_since=updated_since,
    ).offset(offset).limit(limit)
    return list((await session.exec(statement)).all())


async def get_map_by_id(*, session: AsyncSession, id: int) -> Map | None:
    return await session.get(Map, id)


async def get_map_by_name(*, session: AsyncSession, map_name: str) -> Map | None:
    statement = (
        select(Map).where(Map.name == map_name).order_by(col(Map.id).asc()).limit(1)
    )
    return (await session.exec(statement)).first()


async def read_maps_v1(
    *,
    session: AsyncSession,
    offset: int = 0,
    limit: int = 100,
    id: list[int] | None = None,
    name: str | None = None,
    larger_than_filesize: int | None = None,
    smaller_than_filesize: int | None = None,
    is_validated: bool | None = None,
    scope: ModeScope | None = None,
    created_since: datetime | None = None,
    updated_since: datetime | None = None,
) -> list[Map]:
    statement = _build_read_maps_statement(
        id=id,
        name=name,
        larger_than_filesize=larger_than_filesize,
        smaller_than_filesize=smaller_than_filesize,
        is_validated=is_validated,
        difficulty=None,
        scope=scope,
        created_since=created_since,
        updated_since=updated_since,
    ).where(col(Map.id) > 0)

    if is_validated is None:
        statement = statement.where(col(Map.validated).is_(True))

    statement = statement.offset(offset).limit(limit)
    return list((await session.exec(statement)).all())


async def read_admin_maps(
    *,
    session: AsyncSession,
    offset: int = 0,
    limit: int = 20,
    q: str | None = None,
    validated: bool | None = None,
) -> tuple[list[Map], int]:
    statement = select(Map)
    count_statement = select(func.count()).select_from(Map)

    filters = []
    if q:
        filters.append(col(Map.name).ilike(f"%{q}%"))
    if validated is not None:
        filters.append(col(Map.validated) == validated)

    if filters:
        statement = statement.where(*filters)
        count_statement = count_statement.where(*filters)

    count = (await session.exec(count_statement)).one()
    maps = list(
        (
            await session.exec(
                statement.order_by(col(Map.name).asc(), col(Map.id).asc())
                .offset(offset)
                .limit(limit)
            )
        ).all()
    )
    return maps, count


async def load_map_download_urls(
    *, session: AsyncSession, map_ids: list[int]
) -> dict[int, str]:
    if not map_ids:
        return {}
    rows = await session.exec(
        select(MapFileDistribution.map_id, MapFileDistribution.bsp_download_url).where(
            col(MapFileDistribution.map_id).in_(map_ids)
        )
    )
    return {
        map_id: download_url
        for map_id, download_url in rows.all()
        if download_url
    }


async def load_map_bonus_counts(
    *, session: AsyncSession, map_ids: list[int]
) -> dict[int, int]:
    if not map_ids:
        return {}

    rows = await session.exec(
        select(MapCourse.map_id, func.max(MapCourse.stage)).where(
            col(MapCourse.map_id).in_(map_ids)
        ).group_by(MapCourse.map_id)
    )
    return {
        int(map_id): max(int(max_stage or 0), 0)
        for map_id, max_stage in rows.all()
    }


def to_map_compat_public_v0(
    *, map_obj: Map, download_url: str | None = None
) -> MapCompatPublicV0:
    return MapCompatPublicV0(
        id=map_obj.id,
        name=map_obj.name,
        filesize=map_obj.filesize,
        validated=map_obj.validated,
        difficulty=map_obj.difficulty,
        created_on=map_obj.created_at,
        updated_on=map_obj.updated_at,
        approved_by_steamid64=str(map_obj.approved_by_steamid64),
        workshop_id=map_obj.workshop_id,
        download_url=download_url or "",
    )


def to_map_public(
    *,
    map_obj: Map,
    tiers: MapTiers,
    review_summary: MapReviewSummaryPublic | None,
    bonus_count: int = 0,
    download_url: str | None = None,
) -> MapPublic:
    return MapPublic(
        id=map_obj.id,
        name=map_obj.name,
        filesize=map_obj.filesize,
        validated=map_obj.validated,
        tiers=tiers,
        bonus_count=bonus_count,
        created_on=map_obj.created_at,
        updated_on=map_obj.updated_at,
        approved_by_steamid64=str(map_obj.approved_by_steamid64),
        workshop_id=map_obj.workshop_id,
        download_url=download_url,
        synced_at=map_obj.synced_at,
        authors=map_obj.authors or [],
        no_steamid_names=map_obj.no_steamid_names or [],
        review_summary=review_summary,
    )


def to_admin_map_public(*, map_obj: Map, tiers: MapTiers) -> AdminMapPublic:
    return AdminMapPublic(
        id=map_obj.id,
        name=map_obj.name,
        filesize=map_obj.filesize,
        validated=map_obj.validated,
        tiers=tiers,
        difficulty=map_obj.difficulty,
        created_on=map_obj.created_at,
        updated_on=map_obj.updated_at,
        approved_by_steamid64=str(map_obj.approved_by_steamid64),
        workshop_id=map_obj.workshop_id,
        authors=map_obj.authors or [],
        no_steamid_names=map_obj.no_steamid_names or [],
        synced_at=map_obj.synced_at,
    )


async def to_admin_map_publics(
    *, session: AsyncSession, maps: list[Map]
) -> list[AdminMapPublic]:
    if not maps:
        return []

    tiers_by_map_id = await load_map_tiers_by_scope(
        session=session,
        map_ids=[map_obj.id for map_obj in maps],
    )
    return [
        to_admin_map_public(
            map_obj=map_obj,
            tiers=tiers_by_map_id.get(
                map_obj.id,
                MapTiers(),
            ),
        )
        for map_obj in maps
    ]


async def to_map_publics(*, session: AsyncSession, maps: list[Map]) -> list[MapPublic]:
    if not maps:
        return []

    tiers_by_map_id = await load_map_tiers_by_scope(
        session=session,
        map_ids=[map_obj.id for map_obj in maps],
    )
    review_summaries_by_map_id = await load_map_review_summaries(
        session=session,
        map_ids=[map_obj.id for map_obj in maps],
    )
    download_urls_by_map_id = await load_map_download_urls(
        session=session,
        map_ids=[map_obj.id for map_obj in maps],
    )
    bonus_counts_by_map_id = await load_map_bonus_counts(
        session=session,
        map_ids=[map_obj.id for map_obj in maps],
    )
    return [
        to_map_public(
            map_obj=map_obj,
            tiers=tiers_by_map_id.get(
                map_obj.id,
                MapTiers(),
            ),
            review_summary=review_summaries_by_map_id.get(map_obj.id),
            bonus_count=bonus_counts_by_map_id.get(map_obj.id, 0),
            download_url=download_urls_by_map_id.get(map_obj.id),
        )
        for map_obj in maps
    ]
