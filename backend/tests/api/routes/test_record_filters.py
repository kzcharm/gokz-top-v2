from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlmodel import delete
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import RecordFilter


async def _create_record_filter(
    db: AsyncSession,
    *,
    id: int,
    map_id: int,
    stage: int,
    mode_id: int,
    tickrate: int = 128,
    has_teleports: bool = False,
    updated_by_id: str | None = "0",
) -> RecordFilter:
    await db.exec(delete(RecordFilter).where(RecordFilter.id == id))
    await db.commit()

    record_filter = RecordFilter(
        id=id,
        map_id=map_id,
        stage=stage,
        mode_id=mode_id,
        tickrate=tickrate,
        has_teleports=has_teleports,
        created_on=datetime(2021, 1, 1, tzinfo=UTC),
        updated_on=datetime(2021, 1, 2, tzinfo=UTC),
        updated_by_id=updated_by_id,
    )
    db.add(record_filter)
    await db.commit()
    await db.refresh(record_filter)
    return record_filter


@pytest.mark.asyncio
async def test_read_record_filters_v0_contract(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    await _create_record_filter(
        db,
        id=930500,
        map_id=930200,
        stage=0,
        mode_id=200,
        has_teleports=False,
    )

    response = await client.get("/v0/record_filters", params={"ids": 930500})

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": 930500,
            "map_id": 930200,
            "stage": 0,
            "mode_id": 200,
            "tickrate": 128,
            "has_teleports": False,
            "created_on": "2021-01-01T00:00:00Z",
            "updated_on": "2021-01-02T00:00:00Z",
            "updated_by_id": "0",
        }
    ]


@pytest.mark.asyncio
async def test_read_record_filters_v0_supports_filters_and_ordering(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    await _create_record_filter(
        db,
        id=930510,
        map_id=930201,
        stage=1,
        mode_id=200,
        has_teleports=True,
    )
    await _create_record_filter(
        db,
        id=930511,
        map_id=930201,
        stage=1,
        mode_id=200,
        has_teleports=False,
    )
    await _create_record_filter(
        db,
        id=930512,
        map_id=-1,
        stage=1,
        mode_id=201,
        tickrate=64,
        has_teleports=False,
    )

    filtered = await client.get(
        "/v0/record_filters",
        params=[
            ("map_ids", 930201),
            ("stages", 1),
            ("mode_ids", 200),
            ("tickrates", 128),
            ("has_teleports", False),
        ],
    )
    assert filtered.status_code == 200
    assert [row["id"] for row in filtered.json()] == [930511]

    paginated = await client.get(
        "/v0/record_filters",
        params=[
            ("ids", 930510),
            ("ids", 930511),
            ("ids", 930512),
            ("offset", 1),
            ("limit", 2),
        ],
    )
    assert paginated.status_code == 200
    assert [row["id"] for row in paginated.json()] == [930511, 930512]


@pytest.mark.asyncio
async def test_read_record_filters_v0_returns_wildcard_rows(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    await _create_record_filter(
        db,
        id=930520,
        map_id=-1,
        stage=0,
        mode_id=202,
        has_teleports=False,
        updated_by_id=None,
    )

    response = await client.get(
        "/v0/record_filters",
        params=[("ids", 930520), ("map_ids", -1)],
    )

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": 930520,
            "map_id": -1,
            "stage": 0,
            "mode_id": 202,
            "tickrate": 128,
            "has_teleports": False,
            "created_on": "2021-01-01T00:00:00Z",
            "updated_on": "2021-01-02T00:00:00Z",
            "updated_by_id": None,
        }
    ]
