from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx
import pytest
from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import (
    GlobalApiSyncState,
    Map,
    Player,
    PlayerProfileHistory,
    Record,
    ServerGlobalapi,
)
from app.services import globalapi_record_sync as record_sync
from tests.utils.utils import random_steamid64

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _disable_missing_id_backfill_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _unlocked_country(*args: object, **kwargs: object) -> bool:
        del args, kwargs
        return False

    record_sync._missing_record_retry_after.clear()
    monkeypatch.setattr(record_sync, "MISSING_ID_ATTEMPT_LIMIT", 0)
    monkeypatch.setattr(
        record_sync.crud,
        "player_profile_field_change_exists",
        _unlocked_country,
    )


async def _reset_records_sync_state(db: AsyncSession) -> None:
    await db.exec(
        delete(GlobalApiSyncState).where(GlobalApiSyncState.task_name == "records")
    )
    await db.commit()


async def _set_records_cursor(db: AsyncSession, cursor: int) -> None:
    await _reset_records_sync_state(db)
    db.add(GlobalApiSyncState(task_name="records", cursor=cursor))
    await db.commit()


async def _delete_record_by_id(db: AsyncSession, *, record_id: int) -> None:
    await db.exec(delete(Record).where(Record.id == record_id))
    await db.commit()


async def _get_profile_history_rows(
    db: AsyncSession, *, steamid64: int
) -> list[PlayerProfileHistory]:
    return list(
        (
            await db.exec(
                select(PlayerProfileHistory).where(
                    PlayerProfileHistory.player_steamid64 == steamid64
                )
            )
        ).all()
    )


async def _create_local_record(
    db: AsyncSession,
    *,
    record_id: int,
    steamid64: int,
    map_id: int,
    server_id: int,
    points: int = 0,
    created_on: datetime | None = None,
) -> Record:
    await db.exec(delete(Record).where(Record.id == record_id))
    await db.exec(delete(Player).where(Player.steamid64 == steamid64))
    await db.exec(delete(Map).where(Map.id == map_id))
    await db.exec(delete(ServerGlobalapi).where(ServerGlobalapi.id == server_id))
    await db.commit()

    db.add(Player(steamid64=steamid64, name=f"player-{steamid64}"))
    db.add(
        Map(
            id=map_id,
            name=f"map_{map_id}",
            filesize=0,
            validated=False,
            difficulty=0,
            approved_by_steamid64=0,
        )
    )
    db.add(
        ServerGlobalapi(
            id=server_id,
            port=27015,
            ip=None,
            name=f"server_{server_id}",
            owner_steamid64=None,
            approval_status=0,
            approved_by_steamid64=None,
        )
    )
    await db.commit()

    record = Record(
        id=record_id,
        steamid64=steamid64,
        server_id=server_id,
        mode_id=200,
        map_id=map_id,
        stage=0,
        time=Decimal("12.345"),
        teleports=0,
        points=points,
        created_on=created_on or datetime(2026, 1, 1, tzinfo=UTC),
        updated_on=created_on or datetime(2026, 1, 1, tzinfo=UTC),
        updated_by=steamid64,
        replay_id=None,
        is_valid=True,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


def _build_payload(
    *,
    record_id: int,
    steamid64: int,
    map_id: int = 980200,
    server_id: int = 980300,
    player_name: str = "Runner",
    map_name: str = "kz_payload_map",
    server_name: str = "Payload Server",
    points: int = 500,
    created_on: str = "2026-03-30T12:34:56",
    updated_on: str = "2026-03-30T12:35:56",
) -> dict[str, object]:
    return {
        "id": record_id,
        "steamid64": str(steamid64),
        "player_name": player_name,
        "server_id": server_id,
        "server_name": server_name,
        "map_id": map_id,
        "map_name": map_name,
        "stage": 0,
        "mode": "kz_timer",
        "time": 45.678,
        "teleports": 0,
        "points": points,
        "created_on": created_on,
        "updated_on": updated_on,
        "updated_by": str(steamid64),
        "replay_id": 321,
    }


class _StubResponse:
    def __init__(self, *, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> Any:
        return self._payload


async def test_sync_records_from_globalapi_starts_from_largest_local_id_or_200(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _reset_records_sync_state(db)
    steamid64 = random_steamid64()
    await _create_local_record(
        db,
        record_id=981210,
        steamid64=steamid64,
        map_id=981001,
        server_id=981101,
    )

    requested_ids: list[int] = []

    async def _fake_fetch(
        *, client: object, record_id: int
    ) -> record_sync.RecordFetchResult:
        del client
        requested_ids.append(record_id)
        return record_sync.RecordFetchResult(kind="null")

    async def _no_sleep(_: float) -> None:
        return None

    async def _fake_max_record_id(*, session: AsyncSession) -> int:
        del session
        return 981210

    monkeypatch.setattr(record_sync, "_fetch_record_with_retry", _fake_fetch)
    monkeypatch.setattr(record_sync.asyncio, "sleep", _no_sleep)
    monkeypatch.setattr(
        record_sync.crud, "get_max_record_globalapi_id", _fake_max_record_id
    )

    result = await record_sync.sync_records_from_globalapi(session=db)

    assert result == record_sync.GlobalApiSyncResult(
        processed=0,
        created=0,
        updated=0,
        errors=0,
        warnings=0,
    )
    assert requested_ids == [981211, 981212, 981213, 981214, 981215]
    state = await db.get(GlobalApiSyncState, "records")
    assert state is not None
    assert state.cursor == 981211


async def test_sync_records_from_globalapi_skips_existing_ids_even_with_stale_stored_cursor(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _reset_records_sync_state(db)
    steamid64 = random_steamid64()
    await _create_local_record(
        db,
        record_id=981220,
        steamid64=steamid64,
        map_id=981002,
        server_id=981102,
    )
    db.add(GlobalApiSyncState(task_name="records", cursor=777))
    await db.commit()

    requested_ids: list[int] = []

    async def _fake_fetch(
        *, client: object, record_id: int
    ) -> record_sync.RecordFetchResult:
        del client
        requested_ids.append(record_id)
        return record_sync.RecordFetchResult(kind="null")

    async def _no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(record_sync, "_fetch_record_with_retry", _fake_fetch)
    monkeypatch.setattr(record_sync.asyncio, "sleep", _no_sleep)

    await record_sync.sync_records_from_globalapi(session=db)

    assert requested_ids == [981221, 981222, 981223, 981224, 981225]
    state = await db.get(GlobalApiSyncState, "records")
    assert state is not None
    assert state.cursor == 981221


async def test_find_missing_record_ids_in_db_range_skips_existing_local_ids(
    db: AsyncSession,
) -> None:
    await _reset_records_sync_state(db)
    for record_id in (201, 203, 205):
        steamid64 = random_steamid64()
        await _create_local_record(
            db,
            record_id=record_id,
            steamid64=steamid64,
            map_id=record_id + 1000,
            server_id=record_id + 2000,
        )
    missing_ids = await record_sync._find_missing_record_ids_in_db_range(
        session=db,
        start_id=200,
        end_id=205,
        limit=10,
    )

    assert missing_ids == [200, 202, 204]


async def test_sync_records_from_globalapi_backfills_delayed_gap_via_pending_backfill_cursor(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delayed_record_id = 998430
    await _set_records_cursor(db, delayed_record_id)
    record_sync._missing_record_retry_after.clear()
    await _delete_record_by_id(db, record_id=delayed_record_id)
    await _delete_record_by_id(db, record_id=delayed_record_id + 1)
    await _create_local_record(
        db,
        record_id=delayed_record_id - 2,
        steamid64=random_steamid64(),
        map_id=998401,
        server_id=998501,
    )
    await _create_local_record(
        db,
        record_id=delayed_record_id - 1,
        steamid64=random_steamid64(),
        map_id=998402,
        server_id=998502,
    )
    steamid64 = random_steamid64()
    delayed_payload = _build_payload(
        record_id=delayed_record_id,
        steamid64=steamid64,
        map_id=998403,
        server_id=998503,
    )
    probe_payload = _build_payload(
        record_id=delayed_record_id + 1,
        steamid64=random_steamid64(),
        map_id=998404,
        server_id=998504,
    )
    delayed_is_visible = False
    requested_ids: list[int] = []

    async def _fake_fetch(
        *, client: object, record_id: int
    ) -> record_sync.RecordFetchResult:
        del client
        requested_ids.append(record_id)
        if record_id == delayed_record_id and delayed_is_visible:
            return record_sync.RecordFetchResult(kind="record", payload=delayed_payload)
        if record_id == delayed_record_id + 1:
            return record_sync.RecordFetchResult(kind="record", payload=probe_payload)
        return record_sync.RecordFetchResult(kind="null")

    async def _fake_hydrate(
        *, client: object, payload: dict[str, Any]
    ) -> dict[str, Any]:
        del client
        return payload

    async def _fake_player_fetch(_steamid64: int) -> dict[str, str | None]:
        return {
            "name": "Steam Runner",
            "custom_id": None,
            "avatar_hash": None,
            "country": None,
        }

    async def _no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(record_sync, "MISSING_ID_ATTEMPT_LIMIT", 10)
    monkeypatch.setattr(record_sync, "MISSING_IDS_BATCH_SIZE", 10)
    monkeypatch.setattr(record_sync, "_fetch_record_with_retry", _fake_fetch)
    monkeypatch.setattr(
        record_sync, "_hydrate_main_stage_points_from_top", _fake_hydrate
    )
    monkeypatch.setattr(
        record_sync.crud, "_fetch_player_from_steam_api", _fake_player_fetch
    )
    monkeypatch.setattr(record_sync.asyncio, "sleep", _no_sleep)

    first_result = await record_sync.sync_records_from_globalapi(session=db)

    assert first_result.created == 1
    assert (
        await record_sync.crud.get_record_by_id(
            session=db,
            record_id=delayed_record_id,
        )
        is None
    )
    assert (
        await record_sync.crud.get_record_by_id(
            session=db,
            record_id=delayed_record_id + 1,
        )
        is not None
    )
    state = await db.get(GlobalApiSyncState, "records")
    assert state is not None
    assert state.cursor == delayed_record_id + 2
    assert state.pending_backfill_cursor == delayed_record_id

    delayed_is_visible = True
    requested_ids.clear()
    second_result = await record_sync.sync_records_from_globalapi(session=db)

    assert requested_ids[0] == delayed_record_id
    assert second_result.created == 1
    backfilled_record = await record_sync.crud.get_record_by_id(
        session=db,
        record_id=delayed_record_id,
    )
    assert backfilled_record is not None
    assert backfilled_record.steamid64 == steamid64
    state = await db.get(GlobalApiSyncState, "records")
    assert state is not None
    assert state.cursor == delayed_record_id + 2
    assert state.pending_backfill_cursor is None


async def test_sync_records_from_globalapi_uses_stored_cursor_when_ahead_of_local_max(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _reset_records_sync_state(db)
    steamid64 = random_steamid64()
    await _create_local_record(
        db,
        record_id=981230,
        steamid64=steamid64,
        map_id=981003,
        server_id=981103,
    )
    db.add(GlobalApiSyncState(task_name="records", cursor=981500))
    await db.commit()

    requested_ids: list[int] = []

    async def _fake_fetch(
        *, client: object, record_id: int
    ) -> record_sync.RecordFetchResult:
        del client
        requested_ids.append(record_id)
        return record_sync.RecordFetchResult(kind="null")

    async def _no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(record_sync, "_fetch_record_with_retry", _fake_fetch)
    monkeypatch.setattr(record_sync.asyncio, "sleep", _no_sleep)

    await record_sync.sync_records_from_globalapi(session=db)

    assert requested_ids == [981500, 981501, 981502, 981503, 981504]
    state = await db.get(GlobalApiSyncState, "records")
    assert state is not None
    assert state.cursor == 981500


async def test_sync_records_from_globalapi_disables_httpx_env_proxy_by_default(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _set_records_cursor(db, 998100)
    client_kwargs: list[dict[str, Any]] = []

    class _FakeClient:
        def __init__(self, *_: object, **kwargs: Any) -> None:
            client_kwargs.append(kwargs)

        async def __aenter__(self) -> _FakeClient:
            return self

        async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
            del exc_type, exc, tb

    async def _fake_fetch(
        *, client: object, record_id: int
    ) -> record_sync.RecordFetchResult:
        del client, record_id
        return record_sync.RecordFetchResult(kind="null")

    async def _no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(record_sync.httpx, "AsyncClient", _FakeClient)
    monkeypatch.setattr(record_sync, "_fetch_record_with_retry", _fake_fetch)
    monkeypatch.setattr(record_sync.asyncio, "sleep", _no_sleep)

    await record_sync.sync_records_from_globalapi(session=db)

    assert client_kwargs == [
        {
            "timeout": record_sync.settings.GLOBALAPI_TIMEOUT_SECONDS,
            "trust_env": False,
        }
    ]


async def test_sync_records_from_globalapi_creates_dependencies_points_and_uuid_time(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record_id = 998200
    await _set_records_cursor(db, record_id)
    await _delete_record_by_id(db, record_id=record_id)
    steamid64 = random_steamid64()
    payload = _build_payload(record_id=record_id, steamid64=steamid64, points=750)
    expected_created_on = datetime(2026, 3, 30, 12, 34, 56, tzinfo=UTC)

    async def _fake_fetch(
        *, client: object, record_id: int
    ) -> record_sync.RecordFetchResult:
        del client
        if record_id == payload["id"]:
            return record_sync.RecordFetchResult(kind="record", payload=payload)
        return record_sync.RecordFetchResult(kind="null")

    async def _fake_player_fetch(_steamid64: int) -> dict[str, str | None]:
        return {
            "name": "Steam Runner",
            "custom_id": "steam-runner",
            "avatar_hash": "a" * 40,
            "country": "DE",
        }

    async def _no_sleep(_: float) -> None:
        return None

    notified_record_ids: list[str] = []

    async def _fake_notify(*, session: AsyncSession, record_uuid: object) -> None:
        del session
        notified_record_ids.append(str(record_uuid))

    async def _fake_max_record_id(*, session: AsyncSession) -> int:
        del session
        return record_id - 1

    monkeypatch.setattr(record_sync, "_fetch_record_with_retry", _fake_fetch)
    monkeypatch.setattr(
        record_sync.crud, "_fetch_player_from_steam_api", _fake_player_fetch
    )
    monkeypatch.setattr(
        record_sync.crud, "get_max_record_globalapi_id", _fake_max_record_id
    )
    monkeypatch.setattr(record_sync.crud, "notify_recent_record_updated", _fake_notify)
    monkeypatch.setattr(record_sync.asyncio, "sleep", _no_sleep)

    result = await record_sync.sync_records_from_globalapi(session=db)

    assert result.processed == 1
    assert result.created == 1
    assert result.updated == 0
    assert result.errors == 0

    synced_record = await record_sync.crud.get_record_by_id(
        session=db,
        record_id=record_id,
    )
    assert synced_record is not None
    assert synced_record.points == 750
    assert synced_record.uuid.version == 7
    assert synced_record.uuid.time == int(expected_created_on.timestamp() * 1000)
    assert notified_record_ids == [str(synced_record.uuid)]

    player = await db.get(Player, steamid64)
    assert player is not None
    assert player.name == "Steam Runner"
    assert player.last_played_at == expected_created_on

    map_obj = await db.get(Map, payload["map_id"])
    assert map_obj is not None
    server = await db.get(ServerGlobalapi, payload["server_id"])
    assert server is not None

    state = await db.get(GlobalApiSyncState, "records")
    assert state is not None
    assert state.cursor == record_id + 1


async def test_sync_records_from_globalapi_discards_overlong_custom_id(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record_id = 998200
    await _set_records_cursor(db, record_id)
    await _delete_record_by_id(db, record_id=record_id)
    steamid64 = random_steamid64()
    payload = _build_payload(record_id=record_id, steamid64=steamid64, points=750)

    async def _fake_fetch(
        *, client: object, record_id: int
    ) -> record_sync.RecordFetchResult:
        del client
        if record_id == payload["id"]:
            return record_sync.RecordFetchResult(kind="record", payload=payload)
        return record_sync.RecordFetchResult(kind="null")

    async def _fake_player_fetch(_steamid64: int) -> dict[str, str | None]:
        return {
            "name": "Steam Runner",
            "custom_id": "zppppppppppppppppppppppdfff",
            "avatar_hash": "a" * 40,
            "country": "DE",
        }

    async def _no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(record_sync, "_fetch_record_with_retry", _fake_fetch)
    monkeypatch.setattr(
        record_sync.crud, "_fetch_player_from_steam_api", _fake_player_fetch
    )
    monkeypatch.setattr(record_sync.asyncio, "sleep", _no_sleep)

    result = await record_sync.sync_records_from_globalapi(session=db)

    assert result.processed == 1
    assert result.created == 1
    assert result.errors == 0

    player = await db.get(Player, steamid64)
    assert player is not None
    assert player.custom_id is None


async def test_sync_records_from_globalapi_probes_next_ids_after_null(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    start_id = 998200
    success_id = start_id + 2
    await _set_records_cursor(db, start_id)
    await _delete_record_by_id(db, record_id=success_id)
    steamid64 = random_steamid64()
    payload = _build_payload(record_id=success_id, steamid64=steamid64, points=321)
    requested_ids: list[int] = []

    async def _fake_fetch(
        *, client: object, record_id: int
    ) -> record_sync.RecordFetchResult:
        del client
        requested_ids.append(record_id)
        if record_id == success_id:
            return record_sync.RecordFetchResult(kind="record", payload=payload)
        return record_sync.RecordFetchResult(kind="null")

    async def _fake_player_fetch(_steamid64: int) -> dict[str, str | None]:
        return {
            "name": None,
            "custom_id": None,
            "avatar_hash": None,
            "country": None,
        }

    async def _no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(record_sync, "_fetch_record_with_retry", _fake_fetch)
    monkeypatch.setattr(
        record_sync.crud, "_fetch_player_from_steam_api", _fake_player_fetch
    )
    monkeypatch.setattr(record_sync.asyncio, "sleep", _no_sleep)

    result = await record_sync.sync_records_from_globalapi(session=db)

    assert result.processed == 1
    assert requested_ids == [
        start_id,
        start_id + 1,
        start_id + 2,
        start_id + 3,
        start_id + 4,
        start_id + 5,
        start_id + 6,
        start_id + 7,
    ]
    state = await db.get(GlobalApiSyncState, "records")
    assert state is not None
    assert state.cursor == start_id + 3


async def test_fetch_record_with_retry_retries_same_id_after_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []
    sleeps: list[float] = []

    async def _fake_fetch_once(
        *, client: object, record_id: int
    ) -> record_sync.RecordFetchResult:
        del client
        calls.append(record_id)
        if len(calls) == 1:
            raise record_sync.GlobalApiRecordSyncRateLimitError("limited")
        return record_sync.RecordFetchResult(kind="null")

    async def _fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(record_sync, "_fetch_record_once", _fake_fetch_once)
    monkeypatch.setattr(record_sync.asyncio, "sleep", _fake_sleep)

    result = await record_sync._fetch_record_with_retry(client=object(), record_id=200)

    assert result.kind == "null"
    assert calls == [200, 200]
    assert sleeps == [300]


async def test_fetch_record_once_classifies_transport_errors_as_transient() -> None:
    class _FakeClient:
        async def get(self, url: str) -> object:
            del url
            raise httpx.ConnectError("connect failed")

    with pytest.raises(record_sync.GlobalApiRecordSyncTransientError) as exc_info:
        await record_sync._fetch_record_once(client=_FakeClient(), record_id=200)

    assert "Transient failure while fetching record 200" in str(exc_info.value)


async def test_fetch_record_with_retry_retries_same_id_after_transient_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []
    sleeps: list[float] = []

    async def _fake_fetch_once(
        *, client: object, record_id: int
    ) -> record_sync.RecordFetchResult:
        del client
        calls.append(record_id)
        if len(calls) == 1:
            raise record_sync.GlobalApiRecordSyncTransientError("transient")
        return record_sync.RecordFetchResult(kind="null")

    async def _fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(record_sync, "_fetch_record_once", _fake_fetch_once)
    monkeypatch.setattr(record_sync.asyncio, "sleep", _fake_sleep)
    monkeypatch.setattr(record_sync, "TRANSIENT_ERROR_SLEEP_SECONDS", 7)
    monkeypatch.setattr(record_sync, "TRANSIENT_ERROR_RETRY_ATTEMPTS", 3)

    result = await record_sync._fetch_record_with_retry(client=object(), record_id=200)

    assert result.kind == "null"
    assert calls == [200, 200]
    assert sleeps == [7]


async def test_fetch_record_with_retry_raises_after_exhausting_transient_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []
    sleeps: list[float] = []

    async def _fake_fetch_once(
        *, client: object, record_id: int
    ) -> record_sync.RecordFetchResult:
        del client
        calls.append(record_id)
        raise record_sync.GlobalApiRecordSyncTransientError("transient")

    async def _fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(record_sync, "_fetch_record_once", _fake_fetch_once)
    monkeypatch.setattr(record_sync.asyncio, "sleep", _fake_sleep)
    monkeypatch.setattr(record_sync, "TRANSIENT_ERROR_SLEEP_SECONDS", 7)
    monkeypatch.setattr(record_sync, "TRANSIENT_ERROR_RETRY_ATTEMPTS", 3)

    with pytest.raises(record_sync.GlobalApiRecordSyncError) as exc_info:
        await record_sync._fetch_record_with_retry(client=object(), record_id=200)

    assert str(exc_info.value) == (
        "Failed to fetch record 200 from GlobalAPI after 3 transient attempts"
    )
    assert calls == [200, 200, 200]
    assert sleeps == [7, 7]


async def test_sync_records_from_globalapi_counts_malformed_points_and_advances_cursor(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record_id = 998200
    await _set_records_cursor(db, record_id)
    await _delete_record_by_id(db, record_id=record_id)
    steamid64 = random_steamid64()
    payload = _build_payload(record_id=record_id, steamid64=steamid64, points=2001)

    async def _fake_fetch(
        *, client: object, record_id: int
    ) -> record_sync.RecordFetchResult:
        del client
        if record_id == payload["id"]:
            return record_sync.RecordFetchResult(kind="record", payload=payload)
        return record_sync.RecordFetchResult(kind="null")

    async def _no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(record_sync, "_fetch_record_with_retry", _fake_fetch)
    monkeypatch.setattr(record_sync.asyncio, "sleep", _no_sleep)

    result = await record_sync.sync_records_from_globalapi(session=db)

    assert result.processed == 0
    assert result.errors == 1
    assert (
        await record_sync.crud.get_record_by_id(session=db, record_id=record_id) is None
    )
    state = await db.get(GlobalApiSyncState, "records")
    assert state is not None
    assert state.cursor == record_id + 1


async def test_sync_records_from_globalapi_updates_existing_record_without_changing_uuid(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record_id = 998200
    await _set_records_cursor(db, record_id)
    steamid64 = random_steamid64()
    existing = await _create_local_record(
        db,
        record_id=record_id,
        steamid64=steamid64,
        map_id=980201,
        server_id=980301,
        points=0,
        created_on=datetime(2026, 3, 30, 12, 0, 0, tzinfo=UTC),
    )
    payload = _build_payload(
        record_id=record_id,
        steamid64=steamid64,
        map_id=980201,
        server_id=980301,
        points=999,
        player_name="Updated Runner",
    )

    async def _fake_fetch(
        *, client: object, record_id: int
    ) -> record_sync.RecordFetchResult:
        del client
        if record_id == payload["id"]:
            return record_sync.RecordFetchResult(kind="record", payload=payload)
        return record_sync.RecordFetchResult(kind="null")

    async def _fake_player_fetch(_steamid64: int) -> dict[str, str | None]:
        return {
            "name": None,
            "custom_id": None,
            "avatar_hash": None,
            "country": None,
        }

    async def _no_sleep(_: float) -> None:
        return None

    notified_record_ids: list[str] = []

    async def _fake_notify(*, session: AsyncSession, record_uuid: object) -> None:
        del session
        notified_record_ids.append(str(record_uuid))

    async def _fake_max_record_id(*, session: AsyncSession) -> int:
        del session
        return record_id - 1

    monkeypatch.setattr(record_sync, "_fetch_record_with_retry", _fake_fetch)
    monkeypatch.setattr(
        record_sync.crud, "_fetch_player_from_steam_api", _fake_player_fetch
    )
    monkeypatch.setattr(
        record_sync.crud, "get_max_record_globalapi_id", _fake_max_record_id
    )
    monkeypatch.setattr(record_sync.crud, "notify_recent_record_updated", _fake_notify)
    monkeypatch.setattr(record_sync.asyncio, "sleep", _no_sleep)

    result = await record_sync.sync_records_from_globalapi(session=db)

    assert result.processed == 1
    assert result.created == 0
    assert result.updated == 1

    refreshed = await record_sync.crud.get_record_by_id(
        session=db,
        record_id=record_id,
    )
    assert refreshed is not None
    assert refreshed.uuid == existing.uuid
    assert refreshed.points == 999
    assert notified_record_ids == [str(existing.uuid)]


async def test_sync_records_from_globalapi_hydrates_main_stage_points_from_top(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record_id = 998250
    await _set_records_cursor(db, record_id)
    await _delete_record_by_id(db, record_id=record_id)
    steamid64 = random_steamid64()
    payload = _build_payload(record_id=record_id, steamid64=steamid64, points=0)

    async def _fake_fetch(
        *, client: object, record_id: int
    ) -> record_sync.RecordFetchResult:
        del client
        if record_id == payload["id"]:
            return record_sync.RecordFetchResult(kind="record", payload=payload)
        return record_sync.RecordFetchResult(kind="null")

    async def _fake_player_fetch(_steamid64: int) -> dict[str, str | None]:
        return {
            "name": "Steam Runner",
            "custom_id": None,
            "avatar_hash": None,
            "country": None,
        }

    class _FakeClient:
        def __init__(self, *_: object, **__: object) -> None:
            self.top_calls: list[dict[str, Any]] = []

        async def __aenter__(self) -> _FakeClient:
            return self

        async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
            del exc_type, exc, tb

        async def get(
            self,
            url: str,
            params: dict[str, Any] | None = None,
        ) -> _StubResponse:
            if url.endswith(f"/records/{record_id}"):
                return _StubResponse(status_code=200, payload=payload)
            self.top_calls.append({"url": url, "params": params or {}})
            return _StubResponse(
                status_code=200,
                payload=[{"id": record_id, "points": 432}],
            )

    fake_client = _FakeClient()

    async def _no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(record_sync, "_fetch_record_with_retry", _fake_fetch)
    monkeypatch.setattr(
        record_sync.crud, "_fetch_player_from_steam_api", _fake_player_fetch
    )
    monkeypatch.setattr(record_sync.asyncio, "sleep", _no_sleep)
    monkeypatch.setattr(
        record_sync.httpx,
        "AsyncClient",
        lambda *args, **kwargs: fake_client,
    )

    result = await record_sync.sync_records_from_globalapi(session=db)

    assert result.processed == 1
    synced_record = await record_sync.crud.get_record_by_id(
        session=db,
        record_id=record_id,
    )
    assert synced_record is not None
    assert synced_record.points == 432
    assert fake_client.top_calls == [
        {
            "url": f"{record_sync.settings.GLOBALAPI_BASE_URL}/records/top",
            "params": {
                "steamid64": steamid64,
                "map_id": payload["map_id"],
                "stage": 0,
                "modes_list_string": payload["mode"],
                "has_teleports": False,
                "tickrate": 128,
                "limit": 1,
            },
        }
    ]


async def test_sync_records_from_globalapi_skips_top_points_lookup_for_non_main_stage(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record_id = 998260
    await _set_records_cursor(db, record_id)
    await _delete_record_by_id(db, record_id=record_id)
    steamid64 = random_steamid64()
    payload = _build_payload(record_id=record_id, steamid64=steamid64, points=0)
    payload["stage"] = 3

    async def _fake_fetch(
        *, client: object, record_id: int
    ) -> record_sync.RecordFetchResult:
        del client
        if record_id == payload["id"]:
            return record_sync.RecordFetchResult(kind="record", payload=payload)
        return record_sync.RecordFetchResult(kind="null")

    async def _fake_player_fetch(_steamid64: int) -> dict[str, str | None]:
        return {
            "name": "Steam Runner",
            "custom_id": None,
            "avatar_hash": None,
            "country": None,
        }

    top_calls: list[dict[str, Any]] = []

    class _FakeClient:
        async def __aenter__(self) -> _FakeClient:
            return self

        async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
            del exc_type, exc, tb

        async def get(
            self,
            url: str,
            params: dict[str, Any] | None = None,
        ) -> _StubResponse:
            top_calls.append({"url": url, "params": params or {}})
            return _StubResponse(status_code=200, payload=[])

    async def _no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(record_sync, "_fetch_record_with_retry", _fake_fetch)
    monkeypatch.setattr(
        record_sync.crud, "_fetch_player_from_steam_api", _fake_player_fetch
    )
    monkeypatch.setattr(record_sync.asyncio, "sleep", _no_sleep)
    monkeypatch.setattr(
        record_sync.httpx,
        "AsyncClient",
        lambda *args, **kwargs: _FakeClient(),
    )

    result = await record_sync.sync_records_from_globalapi(session=db)

    assert result.processed == 1
    synced_record = await record_sync.crud.get_record_by_id(
        session=db,
        record_id=record_id,
    )
    assert synced_record is not None
    assert synced_record.points == 0
    assert top_calls == []


async def test_hydrate_main_stage_points_from_top_does_not_retry_on_rate_limit() -> (
    None
):
    payload = _build_payload(record_id=998270, steamid64=random_steamid64(), points=0)
    calls: list[dict[str, Any]] = []

    class _FakeClient:
        async def get(
            self,
            url: str,
            params: dict[str, Any] | None = None,
        ) -> _StubResponse:
            calls.append({"url": url, "params": params or {}})
            return _StubResponse(status_code=429, payload={"detail": "limited"})

    hydrated = await record_sync._hydrate_main_stage_points_from_top(
        client=_FakeClient(),
        payload=payload,
    )

    assert hydrated is payload
    assert calls == [
        {
            "url": f"{record_sync.settings.GLOBALAPI_BASE_URL}/records/top",
            "params": {
                "steamid64": int(payload["steamid64"]),
                "map_id": payload["map_id"],
                "stage": 0,
                "modes_list_string": payload["mode"],
                "has_teleports": False,
                "tickrate": 128,
                "limit": 1,
            },
        }
    ]


async def test_sync_records_from_globalapi_emits_debug_logs_for_synced_records(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record_id = 998300
    await _set_records_cursor(db, record_id)
    await _delete_record_by_id(db, record_id=record_id)
    steamid64 = random_steamid64()
    payload = _build_payload(record_id=record_id, steamid64=steamid64, points=444)

    async def _fake_fetch(
        *, client: object, record_id: int
    ) -> record_sync.RecordFetchResult:
        del client
        if record_id == payload["id"]:
            return record_sync.RecordFetchResult(kind="record", payload=payload)
        return record_sync.RecordFetchResult(kind="null")

    async def _fake_player_fetch(_steamid64: int) -> dict[str, str | None]:
        return {
            "name": "Steam Runner",
            "custom_id": None,
            "avatar_hash": None,
            "country": None,
        }

    async def _fake_notify(*, session: AsyncSession, record_uuid: object) -> None:
        del session, record_uuid

    async def _no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(record_sync, "_fetch_record_with_retry", _fake_fetch)
    monkeypatch.setattr(
        record_sync.crud, "_fetch_player_from_steam_api", _fake_player_fetch
    )
    monkeypatch.setattr(record_sync.crud, "notify_recent_record_updated", _fake_notify)
    monkeypatch.setattr(record_sync.asyncio, "sleep", _no_sleep)

    debug_messages: list[str] = []
    info_messages: list[str] = []

    def _capture_debug(message: str, *args: object, **kwargs: object) -> None:
        del kwargs
        debug_messages.append(message % args if args else message)

    def _capture_info(message: str, *args: object, **kwargs: object) -> None:
        del kwargs
        info_messages.append(message % args if args else message)

    monkeypatch.setattr(record_sync.logger, "debug", _capture_debug)
    monkeypatch.setattr(record_sync.logger, "info", _capture_info)

    await record_sync.sync_records_from_globalapi(session=db)

    assert f"Fetching GlobalAPI record record_id={record_id}" in debug_messages
    assert any(
        message.startswith(
            f"Synced GlobalAPI record record_id={record_id} action=created"
        )
        for message in debug_messages
    )
    assert (
        f"Finished GlobalAPI records sync at cursor={record_id + 1} processed=1 created=1 updated=0 errors=0 warnings=0"
        in info_messages
    )


async def test_ensure_player_records_profile_history_for_name_only_change(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    steamid64 = random_steamid64()
    db.add(
        Player(
            steamid64=steamid64,
            name=str(steamid64),
            avatar_hash="a" * 40,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            updated_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    await db.commit()

    async def _fake_fetch_player_from_steam_api(
        _steamid64: int,
    ) -> dict[str, str | bool | None]:
        return {
            "name": "Resolved Steam Name",
            "custom_id": None,
            "avatar_hash": "a" * 40,
            "country": None,
            "fetched": True,
        }

    monkeypatch.setattr(
        record_sync.crud,
        "_fetch_player_from_steam_api",
        _fake_fetch_player_from_steam_api,
    )

    ensured = await record_sync._ensure_player(
        session=db,
        steamid64=steamid64,
        player_name="Fallback Name",
        created_on=datetime(2026, 2, 1, tzinfo=UTC),
    )
    await db.commit()

    assert ensured.name == "Resolved Steam Name"
    history_rows = await _get_profile_history_rows(db, steamid64=steamid64)
    assert len(history_rows) == 1
    assert history_rows[0].name == str(steamid64)
    assert history_rows[0].avatar_hash == "a" * 40
