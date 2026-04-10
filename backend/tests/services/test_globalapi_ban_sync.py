from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Ban, BanType, GlobalApiSyncState
from app.services import globalapi_ban_sync

pytestmark = pytest.mark.asyncio


def _payload(
    *,
    ban_id: int,
    steamid64: int,
    ban_type: str = "bhop_hack",
    updated_on: str = "2026-04-05T12:00:00+00:00",
) -> dict[str, Any]:
    return {
        "id": ban_id,
        "ban_type": ban_type,
        "expires_on": None,
        "ip": "203.0.113.1",
        "steamid64": str(steamid64),
        "player_name": f"Player {steamid64}",
        "notes": "notes",
        "stats": "stats",
        "server_id": 1,
        "updated_by_id": "1",
        "created_on": "2026-04-05T11:00:00+00:00",
        "updated_on": updated_on,
    }


async def _clear_ban_sync_state(db: AsyncSession) -> None:
    await db.exec(delete(Ban))
    await db.exec(
        delete(GlobalApiSyncState).where(GlobalApiSyncState.task_name == "bans")
    )
    await db.commit()


async def test_sync_bans_from_globalapi_backfills_with_large_limit(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _clear_ban_sync_state(db)
    calls: list[tuple[int, int, datetime | None]] = []

    async def _fake_fetch(
        *,
        client: object,
        offset: int,
        limit: int,
        updated_since: datetime | None = None,
    ) -> list[dict[str, Any]]:
        del client
        calls.append((offset, limit, updated_since))
        if offset == 0:
            return [
                _payload(ban_id=1, steamid64=76561198000000001),
                _payload(ban_id=2, steamid64=76561198000000002, ban_type="bhop_macro"),
            ]
        return []

    monkeypatch.setattr(globalapi_ban_sync, "fetch_bans_from_globalapi", _fake_fetch)

    result = await globalapi_ban_sync.sync_bans_from_globalapi(session=db)

    assert result.processed == 2
    assert result.created == 2
    assert calls[0] == (0, globalapi_ban_sync.settings.GLOBALAPI_BANS_BACKFILL_LIMIT, None)
    stored = list((await db.exec(select(Ban).order_by(Ban.id.asc()))).all())
    assert [ban.id for ban in stored] == [1, 2]
    assert stored[1].ban_type == BanType.BHOP_MACRO


async def test_sync_bans_from_globalapi_uses_incremental_limit_and_overlap(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _clear_ban_sync_state(db)
    last_successful_at = datetime(2026, 4, 5, 12, 0, tzinfo=UTC)
    db.add(GlobalApiSyncState(task_name="bans", last_successful_at=last_successful_at))
    await db.commit()

    calls: list[tuple[int, int, datetime | None]] = []

    async def _fake_fetch(
        *,
        client: object,
        offset: int,
        limit: int,
        updated_since: datetime | None = None,
    ) -> list[dict[str, Any]]:
        del client
        calls.append((offset, limit, updated_since))
        return [_payload(ban_id=3, steamid64=76561198000000003)]

    monkeypatch.setattr(globalapi_ban_sync, "fetch_bans_from_globalapi", _fake_fetch)

    result = await globalapi_ban_sync.sync_bans_from_globalapi(session=db)

    assert result.processed == 1
    assert calls[0][0] == 0
    assert calls[0][1] == globalapi_ban_sync.settings.GLOBALAPI_BANS_INCREMENTAL_LIMIT
    assert calls[0][2] == last_successful_at - timedelta(
        seconds=globalapi_ban_sync.settings.GLOBALAPI_BANS_INCREMENTAL_OVERLAP_SECONDS
    )


async def test_sync_bans_from_globalapi_pages_incremental_results(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _clear_ban_sync_state(db)
    db.add(
        GlobalApiSyncState(
            task_name="bans",
            last_successful_at=datetime(2026, 4, 5, 12, 0, tzinfo=UTC),
        )
    )
    await db.commit()

    calls: list[int] = []

    async def _fake_fetch(
        *,
        client: object,
        offset: int,
        limit: int,
        updated_since: datetime | None = None,
    ) -> list[dict[str, Any]]:
        del client, updated_since
        calls.append(offset)
        if offset == 0:
            return [
                _payload(ban_id=100 + index, steamid64=76561198000001000 + index)
                for index in range(limit)
            ]
        if offset == limit:
            return [_payload(ban_id=200, steamid64=76561198000002000)]
        return []

    monkeypatch.setattr(globalapi_ban_sync, "fetch_bans_from_globalapi", _fake_fetch)

    result = await globalapi_ban_sync.sync_bans_from_globalapi(session=db)

    assert result.processed == globalapi_ban_sync.settings.GLOBALAPI_BANS_INCREMENTAL_LIMIT + 1
    assert calls == [0, globalapi_ban_sync.settings.GLOBALAPI_BANS_INCREMENTAL_LIMIT]


async def test_sync_bans_from_globalapi_keeps_local_rows_when_upstream_is_empty(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _clear_ban_sync_state(db)
    db.add(
        Ban(
            id=500,
            ban_type=BanType.BHOP_HACK,
            expires_on=None,
            steamid64=76561198000000500,
            player_name="Existing",
            notes="existing",
            stats="existing",
            server_id=1,
            updated_by_id="1",
            created_on=datetime(2026, 4, 1, tzinfo=UTC),
            updated_on=datetime(2026, 4, 1, tzinfo=UTC),
        )
    )
    await db.commit()

    async def _fake_fetch(
        *,
        client: object,
        offset: int,
        limit: int,
        updated_since: datetime | None = None,
    ) -> list[dict[str, Any]]:
        del client, offset, limit, updated_since
        return []

    monkeypatch.setattr(globalapi_ban_sync, "fetch_bans_from_globalapi", _fake_fetch)

    result = await globalapi_ban_sync.sync_bans_from_globalapi(session=db)

    assert result.processed == 0
    assert await db.get(Ban, 500) is not None


async def test_sync_bans_from_globalapi_counts_duplicates_and_invalid_types(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _clear_ban_sync_state(db)
    async def _fake_fetch(
        *,
        client: object,
        offset: int,
        limit: int,
        updated_since: datetime | None = None,
    ) -> list[dict[str, Any]]:
        del client, offset, limit, updated_since
        return [
            _payload(ban_id=700, steamid64=76561198000000700),
            _payload(ban_id=700, steamid64=76561198000000700),
            _payload(ban_id=701, steamid64=76561198000000701, ban_type="unknown"),
        ]

    monkeypatch.setattr(globalapi_ban_sync, "fetch_bans_from_globalapi", _fake_fetch)

    result = await globalapi_ban_sync.sync_bans_from_globalapi(session=db)

    assert result.processed == 1
    assert result.created == 1
    assert result.errors == 1
    assert result.warnings == 1
    assert await db.get(Ban, 700) is not None
    assert await db.get(Ban, 701) is None


async def test_sync_bans_from_globalapi_allows_multiple_permanent_bans_for_one_player(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _clear_ban_sync_state(db)
    async def _fake_fetch(
        *,
        client: object,
        offset: int,
        limit: int,
        updated_since: datetime | None = None,
    ) -> list[dict[str, Any]]:
        del client, offset, limit, updated_since
        return [
            _payload(ban_id=801, steamid64=76561198000000801, ban_type="bhop_hack"),
            _payload(ban_id=802, steamid64=76561198000000801, ban_type="strafe_hack"),
        ]

    monkeypatch.setattr(globalapi_ban_sync, "fetch_bans_from_globalapi", _fake_fetch)

    result = await globalapi_ban_sync.sync_bans_from_globalapi(session=db)

    assert result.processed == 2
    rows = list(
        (
            await db.exec(
                select(Ban).where(Ban.steamid64 == 76561198000000801).order_by(Ban.id.asc())
            )
        ).all()
    )
    assert [row.id for row in rows] == [801, 802]
    assert [row.ban_type for row in rows] == [BanType.BHOP_HACK, BanType.STRAFE_HACK]


async def test_sync_bans_from_globalapi_maps_9999_expiry_to_null(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _clear_ban_sync_state(db)

    async def _fake_fetch(
        *,
        client: object,
        offset: int,
        limit: int,
        updated_since: datetime | None = None,
    ) -> list[dict[str, Any]]:
        del client, offset, limit, updated_since
        return [
            _payload(
                ban_id=901,
                steamid64=76561198000000901,
                updated_on="2026-04-05T12:00:00+00:00",
            )
            | {"expires_on": "9999-12-31T23:59:59+00:00"}
        ]

    monkeypatch.setattr(globalapi_ban_sync, "fetch_bans_from_globalapi", _fake_fetch)

    result = await globalapi_ban_sync.sync_bans_from_globalapi(session=db)

    assert result.processed == 1
    stored = await db.get(Ban, 901)
    assert stored is not None
    assert stored.expires_on is None


async def test_sync_bans_from_globalapi_rebuilds_leaderboards_for_touched_players(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _clear_ban_sync_state(db)
    rebuilt_steamid64s: list[int] = []

    async def _fake_fetch(
        *,
        client: object,
        offset: int,
        limit: int,
        updated_since: datetime | None = None,
    ) -> list[dict[str, Any]]:
        del client, offset, limit, updated_since
        return [
            _payload(ban_id=950, steamid64=76561198000000950),
            _payload(ban_id=951, steamid64=76561198000000951),
        ]

    async def _fake_rebuild_leaderboards(
        *,
        session: AsyncSession,
        scope_ids: list[int] | None = None,
        steamid64s: list[int] | None = None,
    ) -> tuple[int, int, int]:
        del session, scope_ids
        rebuilt_steamid64s.extend(steamid64s or [])
        return 0, 0, 0

    monkeypatch.setattr(globalapi_ban_sync, "fetch_bans_from_globalapi", _fake_fetch)
    monkeypatch.setattr(
        globalapi_ban_sync.crud,
        "rebuild_leaderboard_players",
        _fake_rebuild_leaderboards,
    )

    result = await globalapi_ban_sync.sync_bans_from_globalapi(session=db)

    assert result.processed == 2
    assert rebuilt_steamid64s == [76561198000000950, 76561198000000951]
