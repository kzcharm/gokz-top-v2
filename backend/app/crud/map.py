from datetime import datetime

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Map, MapCompatPublicV0, MapPublic


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
    created_since: datetime | None = None,
    updated_since: datetime | None = None,
) -> list[Map]:
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
    if created_since is not None:
        statement = statement.where(Map.created_on >= created_since)
    if updated_since is not None:
        statement = statement.where(Map.updated_on >= updated_since)

    statement = statement.order_by(col(Map.validated).desc(), col(Map.name).asc())
    statement = statement.offset(offset).limit(limit)
    return list((await session.exec(statement)).all())


async def get_map_by_id(*, session: AsyncSession, id: int) -> Map | None:
    return await session.get(Map, id)


async def get_map_by_name(*, session: AsyncSession, map_name: str) -> Map | None:
    statement = (
        select(Map).where(Map.name == map_name).order_by(col(Map.id).asc()).limit(1)
    )
    return (await session.exec(statement)).first()


def to_map_compat_public_v0(*, map_obj: Map) -> MapCompatPublicV0:
    return MapCompatPublicV0(
        id=map_obj.id,
        name=map_obj.name,
        filesize=map_obj.filesize,
        validated=map_obj.validated,
        difficulty=map_obj.difficulty,
        created_on=map_obj.created_on,
        updated_on=map_obj.updated_on,
        approved_by_steamid64=str(map_obj.approved_by_steamid64),
        workshop_id=map_obj.workshop_id,
    )


def to_map_public(*, map_obj: Map) -> MapPublic:
    return MapPublic(
        id=map_obj.id,
        name=map_obj.name,
        filesize=map_obj.filesize,
        validated=map_obj.validated,
        difficulty=map_obj.difficulty,
        created_on=map_obj.created_on,
        updated_on=map_obj.updated_on,
        approved_by_steamid64=str(map_obj.approved_by_steamid64),
        workshop_id=map_obj.workshop_id,
        synced_at=map_obj.synced_at,
        authors=map_obj.authors or [],
        no_steamid_names=map_obj.no_steamid_names or [],
    )
