from datetime import UTC, datetime

import pytest
from sqlmodel import delete
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.models import RecordFilter

pytestmark = pytest.mark.asyncio


async def _create_record_filter(
    db: AsyncSession,
    *,
    id: int,
    map_id: int,
    stage: int,
    mode_id: int,
    tickrate: int = 128,
    has_teleports: bool = False,
) -> None:
    await db.exec(delete(RecordFilter).where(RecordFilter.id == id))
    await db.commit()
    db.add(
        RecordFilter(
            id=id,
            map_id=map_id,
            stage=stage,
            mode_id=mode_id,
            tickrate=tickrate,
            has_teleports=has_teleports,
            created_on=datetime(2026, 1, 1, tzinfo=UTC),
            updated_on=datetime(2026, 1, 1, tzinfo=UTC),
            updated_by_id="0",
        )
    )
    await db.commit()


async def test_record_filter_exists_for_course_mode_prefers_exact_match(
    db: AsyncSession,
) -> None:
    await _create_record_filter(
        db,
        id=981500,
        map_id=-1,
        stage=0,
        mode_id=200,
        has_teleports=False,
    )
    await _create_record_filter(
        db,
        id=981501,
        map_id=981200,
        stage=0,
        mode_id=200,
        has_teleports=False,
    )

    assert await crud.record_filter_exists_for_course_mode(
        session=db,
        map_id=981200,
        stage=0,
        mode_id=200,
        has_teleports=False,
    )


async def test_record_filter_exists_for_course_mode_uses_wildcard_fallback(
    db: AsyncSession,
) -> None:
    await _create_record_filter(
        db,
        id=981510,
        map_id=-1,
        stage=2,
        mode_id=201,
        has_teleports=True,
    )

    assert await crud.record_filter_exists_for_course_mode(
        session=db,
        map_id=981201,
        stage=2,
        mode_id=201,
        has_teleports=True,
    )


async def test_record_filter_exists_for_course_mode_distinguishes_tp_and_pro(
    db: AsyncSession,
) -> None:
    await _create_record_filter(
        db,
        id=981520,
        map_id=981202,
        stage=1,
        mode_id=202,
        has_teleports=False,
    )

    assert await crud.record_filter_exists_for_course_mode(
        session=db,
        map_id=981202,
        stage=1,
        mode_id=202,
        has_teleports=False,
    )
    assert not await crud.record_filter_exists_for_course_mode(
        session=db,
        map_id=981202,
        stage=1,
        mode_id=202,
        has_teleports=True,
    )


async def test_record_filter_exists_for_course_mode_returns_false_when_missing(
    db: AsyncSession,
) -> None:
    assert not await crud.record_filter_exists_for_course_mode(
        session=db,
        map_id=981203,
        stage=5,
        mode_id=200,
        has_teleports=False,
    )
