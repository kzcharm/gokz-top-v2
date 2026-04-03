from sqlalchemy import case, or_
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import RecordFilter


async def read_record_filters_v0(
    *,
    session: AsyncSession,
    offset: int = 0,
    limit: int = 100,
    ids: list[int] | None = None,
    map_ids: list[int] | None = None,
    stages: list[int] | None = None,
    mode_ids: list[int] | None = None,
    tickrates: list[int] | None = None,
    has_teleports: bool | None = None,
) -> list[RecordFilter]:
    statement = select(RecordFilter)

    if ids:
        statement = statement.where(col(RecordFilter.id).in_(ids))
    if map_ids:
        statement = statement.where(col(RecordFilter.map_id).in_(map_ids))
    if stages:
        statement = statement.where(col(RecordFilter.stage).in_(stages))
    if mode_ids:
        statement = statement.where(col(RecordFilter.mode_id).in_(mode_ids))
    if tickrates:
        statement = statement.where(col(RecordFilter.tickrate).in_(tickrates))
    if has_teleports is not None:
        statement = statement.where(col(RecordFilter.has_teleports) == has_teleports)

    statement = statement.order_by(col(RecordFilter.id).asc()).offset(offset).limit(limit)
    return list((await session.exec(statement)).all())


async def record_filter_exists_for_course_mode(
    *,
    session: AsyncSession,
    map_id: int,
    stage: int,
    mode_id: int,
    tickrate: int = 128,
    has_teleports: bool,
) -> bool:
    statement = (
        select(RecordFilter.id)
        .where(
            col(RecordFilter.stage) == stage,
            col(RecordFilter.mode_id) == mode_id,
            col(RecordFilter.tickrate) == tickrate,
            col(RecordFilter.has_teleports) == has_teleports,
            or_(
                col(RecordFilter.map_id) == map_id,
                col(RecordFilter.map_id) == -1,
            ),
        )
        .order_by(
            case((col(RecordFilter.map_id) == map_id, 0), else_=1),
            col(RecordFilter.id).asc(),
        )
        .limit(1)
    )
    return (await session.exec(statement)).first() is not None
