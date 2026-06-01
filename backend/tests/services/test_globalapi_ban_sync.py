from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Ban, BanType, GlobalApiSyncState, Player
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
        created_since: datetime | None = None,
        updated_since: datetime | None = None,
    ) -> list[dict[str, Any]]:
        del client
        assert updated_since is None
        calls.append((offset, limit, created_since))
        if offset == 0:
            return [
                _payload(ban_id=1, steamid64=76561198000000001),
                _payload(ban_id=2, steamid64=76561198000000002, ban_type="boosting"),
            ]
        return []

    monkeypatch.setattr(globalapi_ban_sync, "fetch_bans_from_globalapi", _fake_fetch)

    result = await globalapi_ban_sync.sync_bans_from_globalapi(session=db)

    assert result.processed == 2
    assert result.created == 2
    assert calls[0] == (
        0,
        globalapi_ban_sync.settings.GLOBALAPI_BANS_BACKFILL_LIMIT,
        None,
    )
    stored = list((await db.exec(select(Ban).order_by(Ban.id.asc()))).all())
    assert [ban.id for ban in stored] == [1, 2]
    assert stored[1].ban_type == BanType.BOOSTING
    player = await db.get(Player, 76561198000000001)
    assert player is not None
    assert player.name == "Player 76561198000000001"


async def test_sync_bans_from_globalapi_uses_incremental_limit_and_overlap(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _clear_ban_sync_state(db)
    last_successful_at = datetime(2026, 4, 5, 12, 0, tzinfo=UTC)
    db.add(GlobalApiSyncState(task_name="bans", last_successful_at=last_successful_at))
    db.add(
        Player(
            steamid64=76561198000000099,
            name="Existing",
        )
    )
    await db.flush()
    db.add(
        Ban(
            id=99,
            ban_type=BanType.BHOP_HACK,
            expires_at=None,
            steamid64=76561198000000099,
            notes="existing",
            stats="existing",
            server_id=1,
            updated_by_steamid64=1,
            created_at=datetime(2026, 4, 5, 10, 0, tzinfo=UTC),
            updated_at=datetime(2026, 4, 5, 11, 0, tzinfo=UTC),
        )
    )
    await db.commit()

    calls: list[tuple[int, int, datetime | None]] = []

    async def _fake_fetch(
        *,
        client: object,
        offset: int,
        limit: int,
        created_since: datetime | None = None,
        updated_since: datetime | None = None,
    ) -> list[dict[str, Any]]:
        del client
        assert updated_since is None
        calls.append((offset, limit, created_since))
        return [_payload(ban_id=3, steamid64=76561198000000003)]

    monkeypatch.setattr(globalapi_ban_sync, "fetch_bans_from_globalapi", _fake_fetch)

    result = await globalapi_ban_sync.sync_bans_from_globalapi(session=db)

    assert result.processed == 1
    assert calls[0][0] == 0
    assert calls[0][1] == globalapi_ban_sync.settings.GLOBALAPI_BANS_INCREMENTAL_LIMIT
    assert calls[0][2] == datetime(2026, 4, 5, 10, 0, tzinfo=UTC) - timedelta(
        seconds=globalapi_ban_sync.settings.GLOBALAPI_BANS_INCREMENTAL_OVERLAP_SECONDS
    )


async def test_sync_bans_from_globalapi_skips_existing_rows_and_preserves_local_edits(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _clear_ban_sync_state(db)
    steamid64 = 76561198000000077
    db.add(Player(steamid64=steamid64, name="Existing"))
    await db.flush()
    db.add(
        Ban(
            id=77,
            ban_type=BanType.BHOP_HACK,
            expires_at=datetime(2026, 4, 20, tzinfo=UTC),
            steamid64=steamid64,
            notes="local note",
            stats="local stats",
            server_id=1,
            updated_by_steamid64=76561198000000001,
            created_at=datetime(2026, 4, 5, 10, 0, tzinfo=UTC),
            updated_at=datetime(2026, 4, 5, 11, 0, tzinfo=UTC),
        )
    )
    await db.commit()

    async def _fake_fetch(
        *,
        client: object,
        offset: int,
        limit: int,
        created_since: datetime | None = None,
        updated_since: datetime | None = None,
    ) -> list[dict[str, Any]]:
        del client, offset, limit, created_since, updated_since
        return [
            _payload(
                ban_id=77,
                steamid64=steamid64,
                updated_on="2026-04-10T12:00:00+00:00",
            )
            | {
                "expires_on": "2026-05-01T00:00:00+00:00",
                "notes": "upstream note",
                "stats": "upstream stats",
                "updated_by_id": "99",
            }
        ]

    monkeypatch.setattr(globalapi_ban_sync, "fetch_bans_from_globalapi", _fake_fetch)

    result = await globalapi_ban_sync.sync_bans_from_globalapi(session=db)

    assert result.processed == 1
    assert result.created == 0
    assert result.updated == 0
    refreshed = (await db.exec(select(Ban).where(Ban.id == 77))).one()
    assert refreshed.notes == "local note"
    assert refreshed.stats == "local stats"
    assert refreshed.expires_at == datetime(2026, 4, 20, tzinfo=UTC)
    assert refreshed.updated_by_steamid64 == 76561198000000001


async def test_sync_bans_from_globalapi_backfills_when_state_exists_but_table_is_empty(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _clear_ban_sync_state(db)
    db.add(
        GlobalApiSyncState(
            task_name="bans",
            last_successful_at=datetime(2026, 4, 14, 20, 18, tzinfo=UTC),
        )
    )
    await db.commit()

    calls: list[tuple[int, int, datetime | None]] = []

    async def _fake_fetch(
        *,
        client: object,
        offset: int,
        limit: int,
        created_since: datetime | None = None,
        updated_since: datetime | None = None,
    ) -> list[dict[str, Any]]:
        del client
        assert updated_since is None
        calls.append((offset, limit, created_since))
        return []

    monkeypatch.setattr(globalapi_ban_sync, "fetch_bans_from_globalapi", _fake_fetch)

    await globalapi_ban_sync.sync_bans_from_globalapi(session=db)

    assert calls == [
        (0, globalapi_ban_sync.settings.GLOBALAPI_BANS_BACKFILL_LIMIT, None)
    ]


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
    db.add(
        Player(
            steamid64=76561198000000098,
            name="Existing",
        )
    )
    await db.flush()
    db.add(
        Ban(
            id=98,
            ban_type=BanType.BHOP_HACK,
            expires_at=None,
            steamid64=76561198000000098,
            notes="existing",
            stats="existing",
            server_id=1,
            updated_by_steamid64=1,
            created_at=datetime(2026, 4, 5, 10, 0, tzinfo=UTC),
            updated_at=datetime(2026, 4, 5, 11, 0, tzinfo=UTC),
        )
    )
    await db.commit()

    calls: list[int] = []

    async def _fake_fetch(
        *,
        client: object,
        offset: int,
        limit: int,
        created_since: datetime | None = None,
        updated_since: datetime | None = None,
    ) -> list[dict[str, Any]]:
        del client, updated_since, created_since
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

    assert (
        result.processed
        == globalapi_ban_sync.settings.GLOBALAPI_BANS_INCREMENTAL_LIMIT + 1
    )
    assert calls == [0, globalapi_ban_sync.settings.GLOBALAPI_BANS_INCREMENTAL_LIMIT]


async def test_sync_bans_from_globalapi_keeps_local_rows_when_upstream_is_empty(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _clear_ban_sync_state(db)
    db.add(
        Player(
            steamid64=76561198000000500,
            name="Existing",
        )
    )
    await db.flush()
    existing_ban = Ban(
        id=500,
        ban_type=BanType.BHOP_HACK,
        expires_at=None,
        steamid64=76561198000000500,
        notes="existing",
        stats="existing",
        server_id=1,
        updated_by_steamid64=1,
        created_at=datetime(2026, 4, 1, tzinfo=UTC),
        updated_at=datetime(2026, 4, 1, tzinfo=UTC),
    )
    db.add(existing_ban)
    await db.commit()
    existing_ban_uuid = existing_ban.uuid

    async def _fake_fetch(
        *,
        client: object,
        offset: int,
        limit: int,
        created_since: datetime | None = None,
        updated_since: datetime | None = None,
    ) -> list[dict[str, Any]]:
        del client, offset, limit, updated_since, created_since
        return []

    monkeypatch.setattr(globalapi_ban_sync, "fetch_bans_from_globalapi", _fake_fetch)

    result = await globalapi_ban_sync.sync_bans_from_globalapi(session=db)

    assert result.processed == 0
    assert await db.get(Ban, existing_ban_uuid) is not None


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
        created_since: datetime | None = None,
        updated_since: datetime | None = None,
    ) -> list[dict[str, Any]]:
        del client, offset, limit, updated_since, created_since
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
    created_ban = (
        await db.exec(select(Ban).where(Ban.id == 700))
    ).first()
    rejected_ban = (
        await db.exec(select(Ban).where(Ban.id == 701))
    ).first()
    assert created_ban is not None
    assert rejected_ban is None
    created_player = await db.get(Player, 76561198000000700)
    assert created_player is not None
    assert created_player.name == "Player 76561198000000700"


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
        created_since: datetime | None = None,
        updated_since: datetime | None = None,
    ) -> list[dict[str, Any]]:
        del client, offset, limit, updated_since, created_since
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
                select(Ban)
                .where(Ban.steamid64 == 76561198000000801)
                .order_by(Ban.id.asc())
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
        created_since: datetime | None = None,
        updated_since: datetime | None = None,
    ) -> list[dict[str, Any]]:
        del client, offset, limit, updated_since, created_since
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
    stored = (await db.exec(select(Ban).where(Ban.id == 901))).first()
    assert stored is not None
    assert stored.expires_at is None


async def test_sync_bans_from_globalapi_does_not_match_manual_local_bans(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _clear_ban_sync_state(db)
    steamid64 = 76561198000000925
    db.add(Player(steamid64=steamid64, name="Manual Local Player"))
    await db.flush()
    manual_ban = Ban(
        ban_type=BanType.BHOP_MACRO,
        expires_at=None,
        steamid64=steamid64,
        notes="manual local ban",
        stats="manual stats",
        updated_by_steamid64=76561198000000001,
        created_at=datetime(2026, 4, 1, tzinfo=UTC),
        updated_at=datetime(2026, 4, 1, tzinfo=UTC),
    )
    db.add(manual_ban)
    await db.commit()
    manual_ban_uuid = manual_ban.uuid

    async def _fake_fetch(
        *,
        client: object,
        offset: int,
        limit: int,
        created_since: datetime | None = None,
        updated_since: datetime | None = None,
    ) -> list[dict[str, Any]]:
        del client, offset, limit, created_since, updated_since
        return [_payload(ban_id=925, steamid64=steamid64)]

    monkeypatch.setattr(globalapi_ban_sync, "fetch_bans_from_globalapi", _fake_fetch)

    result = await globalapi_ban_sync.sync_bans_from_globalapi(session=db)

    assert result.processed == 1
    rows = list(
        (
            await db.exec(
                select(Ban)
                .where(Ban.steamid64 == steamid64)
                .order_by(Ban.created_at.asc(), Ban.uuid.asc())
            )
        ).all()
    )
    assert len(rows) == 2
    assert rows[0].uuid == manual_ban_uuid
    assert rows[0].id is None
    assert rows[0].notes == "manual local ban"
    assert rows[1].id == 925
    assert rows[1].notes == "notes"


async def test_sync_bans_from_globalapi_updates_placeholder_player_name_only(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _clear_ban_sync_state(db)
    db.add(Player(steamid64=76561198000000910, name="76561198000000910"))
    db.add(Player(steamid64=76561198000000911, name="Established Name"))
    await db.commit()

    async def _fake_fetch(
        *,
        client: object,
        offset: int,
        limit: int,
        created_since: datetime | None = None,
        updated_since: datetime | None = None,
    ) -> list[dict[str, Any]]:
        del client, offset, limit, updated_since, created_since
        return [
            _payload(ban_id=910, steamid64=76561198000000910)
            | {"player_name": "Resolved Placeholder"},
            _payload(ban_id=911, steamid64=76561198000000911)
            | {"player_name": "Should Not Replace"},
        ]

    monkeypatch.setattr(globalapi_ban_sync, "fetch_bans_from_globalapi", _fake_fetch)

    result = await globalapi_ban_sync.sync_bans_from_globalapi(session=db)

    assert result.processed == 2
    placeholder_player = await db.get(Player, 76561198000000910)
    assert placeholder_player is not None
    assert placeholder_player.name == "Resolved Placeholder"
    established_player = await db.get(Player, 76561198000000911)
    assert established_player is not None
    assert established_player.name == "Established Name"


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
        created_since: datetime | None = None,
        updated_since: datetime | None = None,
    ) -> list[dict[str, Any]]:
        del client, offset, limit, updated_since, created_since
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


async def test_sync_player_bans_from_globalapi_pages_by_player_and_upserts_updates(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _clear_ban_sync_state(db)
    steamid64 = 76561198000001010
    db.add(Player(steamid64=steamid64, name="Paged Player"))
    await db.flush()
    db.add(
        Ban(
            id=1_010,
            ban_type=BanType.BHOP_HACK,
            expires_at=None,
            steamid64=steamid64,
            notes="existing note",
            stats="existing stats",
            server_id=1,
            updated_by_steamid64=1,
            created_at=datetime(2026, 4, 1, tzinfo=UTC),
            updated_at=datetime(2026, 4, 1, tzinfo=UTC),
        )
    )
    await db.commit()

    monkeypatch.setattr(globalapi_ban_sync.settings, "GLOBALAPI_BANS_BACKFILL_LIMIT", 1)
    calls: list[tuple[int, int, int | None]] = []
    active_until = datetime.now(UTC) + timedelta(days=7)

    async def _fake_fetch(
        *,
        client: object,
        offset: int,
        limit: int,
        steamid64: int | None = None,
        created_since: datetime | None = None,
        updated_since: datetime | None = None,
    ) -> list[dict[str, Any]]:
        del client, created_since, updated_since
        calls.append((offset, limit, steamid64))
        if offset == 0:
            return [
                _payload(
                    ban_id=1_010,
                    steamid64=steamid64 or 0,
                    updated_on="2026-04-06T12:00:00+00:00",
                )
                | {
                    "expires_on": active_until.isoformat(),
                    "notes": "updated note",
                    "stats": "updated stats",
                }
            ]
        if offset == 1:
            return [
                _payload(
                    ban_id=1_011,
                    steamid64=steamid64 or 0,
                    updated_on="2026-04-07T12:00:00+00:00",
                )
            ]
        return []

    monkeypatch.setattr(globalapi_ban_sync, "fetch_bans_from_globalapi", _fake_fetch)

    result = await globalapi_ban_sync.sync_player_bans_from_globalapi(
        session=db,
        steamid64=steamid64,
    )

    assert result.cleared_active_ban_count == 0
    assert result.remaining_active_ban_count == 2
    assert calls == [(0, 1, steamid64), (1, 1, steamid64), (2, 1, steamid64)]

    rows = list(
        (
            await db.exec(
                select(Ban)
                .where(Ban.steamid64 == steamid64)
                .order_by(Ban.id.asc())
            )
        ).all()
    )
    assert [row.id for row in rows] == [1_010, 1_011]
    assert rows[0].notes == "updated note"
    assert rows[0].stats == "updated stats"
    assert rows[0].expires_at == active_until
    assert rows[0].updated_by_steamid64 == 1


async def test_sync_player_bans_from_globalapi_clears_active_ban_without_duplicates(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _clear_ban_sync_state(db)
    steamid64 = 76561198000001011
    db.add(Player(steamid64=steamid64, name="Cleared Player"))
    await db.flush()
    db.add(
        Ban(
            id=1_020,
            ban_type=BanType.BHOP_HACK,
            expires_at=None,
            steamid64=steamid64,
            notes="existing",
            stats="existing",
            server_id=1,
            updated_by_steamid64=1,
            created_at=datetime(2026, 4, 1, tzinfo=UTC),
            updated_at=datetime(2026, 4, 1, tzinfo=UTC),
        )
    )
    await db.commit()

    expired_at = datetime.now(UTC) - timedelta(hours=1)
    rebuilt_steamid64s: list[int] = []

    async def _fake_fetch(
        *,
        client: object,
        offset: int,
        limit: int,
        steamid64: int | None = None,
        created_since: datetime | None = None,
        updated_since: datetime | None = None,
    ) -> list[dict[str, Any]]:
        del client, limit, created_since, updated_since
        if offset > 0:
            return []
        return [
            _payload(
                ban_id=1_020,
                steamid64=steamid64 or 0,
                updated_on="2026-04-08T12:00:00+00:00",
            )
            | {
                "expires_on": expired_at.isoformat(),
                "notes": "expired",
            }
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

    result = await globalapi_ban_sync.sync_player_bans_from_globalapi(
        session=db,
        steamid64=steamid64,
    )

    assert result.cleared_active_ban_count == 1
    assert result.remaining_active_ban_count == 0
    assert rebuilt_steamid64s == [steamid64]

    rows = list(
        (
            await db.exec(
                select(Ban)
                .where(Ban.steamid64 == steamid64)
                .order_by(Ban.id.asc())
            )
        ).all()
    )
    assert len(rows) == 1
    assert rows[0].id == 1_020
    assert rows[0].expires_at == expired_at


async def test_sync_player_bans_from_globalapi_ignores_manual_bans_for_status_counts(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _clear_ban_sync_state(db)
    steamid64 = 76561198000001012
    db.add(Player(steamid64=steamid64, name="Mixed Ban Player"))
    await db.flush()
    mirrored_ban = Ban(
        id=1_021,
        ban_type=BanType.BHOP_HACK,
        expires_at=None,
        steamid64=steamid64,
        notes="mirrored",
        stats="mirrored",
        server_id=1,
        updated_by_steamid64=1,
        created_at=datetime(2026, 4, 1, tzinfo=UTC),
        updated_at=datetime(2026, 4, 1, tzinfo=UTC),
    )
    manual_ban = Ban(
        ban_type=BanType.BHOP_MACRO,
        expires_at=None,
        steamid64=steamid64,
        notes="manual",
        stats="manual",
        updated_by_steamid64=76561198000000001,
        created_at=datetime(2026, 4, 2, tzinfo=UTC),
        updated_at=datetime(2026, 4, 2, tzinfo=UTC),
    )
    db.add(mirrored_ban)
    db.add(manual_ban)
    await db.commit()
    manual_ban_uuid = manual_ban.uuid

    expired_at = datetime.now(UTC) - timedelta(hours=1)

    async def _fake_fetch(
        *,
        client: object,
        offset: int,
        limit: int,
        steamid64: int | None = None,
        created_since: datetime | None = None,
        updated_since: datetime | None = None,
    ) -> list[dict[str, Any]]:
        del client, limit, created_since, updated_since
        if offset > 0:
            return []
        return [
            _payload(
                ban_id=1_021,
                steamid64=steamid64 or 0,
                updated_on="2026-04-08T12:00:00+00:00",
            )
            | {
                "expires_on": expired_at.isoformat(),
                "notes": "expired mirrored",
            }
        ]

    monkeypatch.setattr(globalapi_ban_sync, "fetch_bans_from_globalapi", _fake_fetch)

    result = await globalapi_ban_sync.sync_player_bans_from_globalapi(
        session=db,
        steamid64=steamid64,
    )

    assert result.cleared_active_ban_count == 1
    assert result.remaining_active_ban_count == 0

    refreshed_manual = await db.get(Ban, manual_ban_uuid)
    assert refreshed_manual is not None
    assert refreshed_manual.expires_at is None
    assert refreshed_manual.notes == "manual"
