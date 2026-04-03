from datetime import UTC, datetime
from typing import Any

import pytest
from sqlmodel import delete
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import RecordFilter
from app.services import globalapi_record_filter_sync as record_filter_sync

pytestmark = pytest.mark.asyncio


async def _create_local_record_filter(
    db: AsyncSession,
    *,
    id: int,
    map_id: int = 980200,
    stage: int = 0,
    mode_id: int = 200,
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
        created_on=datetime(2024, 1, 1, tzinfo=UTC),
        updated_on=datetime(2024, 1, 2, tzinfo=UTC),
        updated_by_id=updated_by_id,
    )
    db.add(record_filter)
    await db.commit()
    await db.refresh(record_filter)
    return record_filter


def _payload(
    *,
    id: int,
    map_id: int,
    stage: int,
    mode_id: int,
    tickrate: int = 128,
    has_teleports: bool = False,
    updated_by_id: str | None = "0",
) -> dict[str, Any]:
    return {
        "id": id,
        "map_id": map_id,
        "stage": stage,
        "mode_id": mode_id,
        "tickrate": tickrate,
        "has_teleports": has_teleports,
        "created_on": "2020-10-03T00:07:53",
        "updated_on": "2020-10-03T00:07:53",
        "updated_by_id": updated_by_id,
    }


async def test_sync_record_filters_from_globalapi_syncs_multiple_pages(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_fetch(
        *,
        client: object | None = None,
        offset: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        del client
        assert limit == 2
        pages = {
            0: [
                _payload(id=981600, map_id=981200, stage=0, mode_id=200),
                _payload(id=981601, map_id=981201, stage=1, mode_id=201),
            ],
            2: [
                _payload(id=981602, map_id=-1, stage=2, mode_id=202),
            ],
        }
        return pages.get(offset, [])

    monkeypatch.setattr(
        record_filter_sync.settings,
        "GLOBALAPI_RECORD_FILTERS_LIMIT",
        2,
    )
    monkeypatch.setattr(record_filter_sync, "fetch_record_filters_from_globalapi", _fake_fetch)

    result = await record_filter_sync.sync_record_filters_from_globalapi(session=db)

    assert result == record_filter_sync.GlobalApiSyncResult(
        processed=3,
        created=3,
        updated=0,
        errors=0,
        warnings=0,
    )
    assert await db.get(RecordFilter, 981600) is not None
    assert await db.get(RecordFilter, 981601) is not None
    wildcard = await db.get(RecordFilter, 981602)
    assert wildcard is not None
    assert wildcard.map_id == -1


async def test_sync_record_filters_from_globalapi_updates_existing_rows(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _create_local_record_filter(
        db,
        id=981610,
        map_id=981210,
        stage=0,
        mode_id=200,
        has_teleports=False,
    )

    async def _fake_fetch(
        *,
        client: object | None = None,
        offset: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        del client, limit
        if offset > 0:
            return []
        return [
            _payload(
                id=981610,
                map_id=981211,
                stage=3,
                mode_id=201,
                has_teleports=True,
                updated_by_id="76561198000000001",
            )
        ]

    monkeypatch.setattr(record_filter_sync, "fetch_record_filters_from_globalapi", _fake_fetch)

    result = await record_filter_sync.sync_record_filters_from_globalapi(session=db)

    assert result.processed == 1
    assert result.created == 0
    assert result.updated == 1
    synced = await db.get(RecordFilter, 981610)
    assert synced is not None
    assert synced.map_id == 981211
    assert synced.stage == 3
    assert synced.mode_id == 201
    assert synced.has_teleports is True
    assert synced.updated_by_id == "76561198000000001"


async def test_sync_record_filters_from_globalapi_skips_malformed_rows(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_fetch(
        *,
        client: object | None = None,
        offset: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        del client, limit
        if offset > 0:
            return []
        return [
            {
                "id": 981620,
                "map_id": 981220,
                "stage": 0,
                "mode_id": 200,
                "tickrate": 0,
            },
            _payload(id=981621, map_id=981221, stage=0, mode_id=200),
        ]

    monkeypatch.setattr(record_filter_sync, "fetch_record_filters_from_globalapi", _fake_fetch)

    result = await record_filter_sync.sync_record_filters_from_globalapi(session=db)

    assert result.processed == 1
    assert result.created == 1
    assert result.errors == 1
    assert await db.get(RecordFilter, 981620) is None
    assert await db.get(RecordFilter, 981621) is not None


async def test_sync_record_filters_from_globalapi_ignores_duplicate_ids_with_warning(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_fetch(
        *,
        client: object | None = None,
        offset: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        del client, limit
        if offset > 0:
            return []
        return [
            _payload(id=981630, map_id=981230, stage=0, mode_id=200),
            _payload(id=981630, map_id=981231, stage=1, mode_id=201),
        ]

    monkeypatch.setattr(record_filter_sync, "fetch_record_filters_from_globalapi", _fake_fetch)

    result = await record_filter_sync.sync_record_filters_from_globalapi(session=db)

    assert result.processed == 1
    assert result.created == 1
    assert result.warnings == 1
    synced = await db.get(RecordFilter, 981630)
    assert synced is not None
    assert synced.map_id == 981230


async def test_sync_record_filters_from_globalapi_keeps_rows_missing_upstream(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _create_local_record_filter(db, id=981640, map_id=981240, stage=0, mode_id=200)

    async def _fake_fetch(
        *,
        client: object | None = None,
        offset: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        del client, limit
        if offset > 0:
            return []
        return [_payload(id=981641, map_id=981241, stage=0, mode_id=200)]

    monkeypatch.setattr(record_filter_sync, "fetch_record_filters_from_globalapi", _fake_fetch)

    result = await record_filter_sync.sync_record_filters_from_globalapi(session=db)

    assert result.processed == 1
    assert await db.get(RecordFilter, 981640) is not None
    assert await db.get(RecordFilter, 981641) is not None
