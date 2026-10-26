import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import (
    KZMode,
    Map,
    MapCourse,
    MapCourseTier,
    Mode,
    ModeScope,
    Player,
    PlayerStatCache,
    PlayerStatType,
    Record,
    RecordFilter,
    RecordPb,
    ServerGroupStatus,
    generate_uuid7,
    get_datetime_utc,
    mode_scope_modes,
)
from app.models.record_upload import RecordFinish, RecordIntegrity
from app.services.record_ingestion import accept_record, check_record
from tests.utils.server import create_server, create_server_group


async def setup_finish(db: AsyncSession, mode: KZMode = KZMode.NKZ):
    group, _ = await create_server_group(db, status=ServerGroupStatus.VALIDATED)
    server = await create_server(db, group_id=group.id)
    map_obj = Map(id=982345, name="kz_direct_records", filesize=123, validated=True)
    db.add(map_obj)
    await db.flush()
    course = MapCourse(map_id=map_obj.id, stage=0)
    db.add(course)
    await db.flush()
    db.add(
        MapCourseTier(
            course_id=course.id, mode=KZMode.KZT if mode == KZMode.NKZ else mode, tier=1
        )
    )
    db.add(
        RecordFilter(
            id=982345,
            map_id=map_obj.id,
            stage=0,
            mode=KZMode.KZT if mode == KZMode.NKZ else mode,
            tickrate=128,
            has_teleports=True,
        )
    )
    await db.flush()
    version = (
        (await db.exec(select(Mode).where(Mode.name_short == mode)))
        .one()
        .latest_version
    )
    payload = RecordFinish(
        server_id=server.id,
        map_name=map_obj.name,
        bsp_size=123,
        mode=mode,
        mode_version=version,
        steamid64=76561197960278073,
        integrity=RecordIntegrity(**dict.fromkeys(RecordIntegrity.model_fields, True)),
        time=Decimal("35.289"),
        teleports=0,
        finished_at=get_datetime_utc(),
        record_uuid=generate_uuid7(),
    )
    return group, server, payload


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", list(KZMode))
async def test_accept_all_modes_and_retry(db: AsyncSession, mode: KZMode):
    group, server, payload = await setup_finish(db, mode)
    result = await accept_record(db, group, payload, "finish-1")
    assert result["replay_eligible"] is True
    assert result["record_uuid"] == str(payload.record_uuid)
    assert await accept_record(db, group, payload, "finish-1") == result
    record = await db.get(Record, uuid.UUID(result["record_uuid"]))
    assert record.native_server_id == server.id
    assert record.server_id is None
    assert record.mode == mode
    player = await db.get(Player, payload.steamid64)
    assert player.last_played_at == payload.finished_at
    assert player.created_at == payload.finished_at
    pbs = (
        await db.exec(select(RecordPb).where(RecordPb.record_uuid == record.uuid))
    ).all()
    assert {row.scope for row in pbs} == {
        scope for scope in ModeScope if mode in mode_scope_modes(scope)
    }
    assert {row.points for row in pbs} == {1000}
    with pytest.raises(HTTPException) as error:
        await accept_record(
            db,
            group,
            payload.model_copy(update={"time": Decimal("34.000")}),
            "finish-1",
        )
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_ties_are_distinct_and_not_replay_eligible(db: AsyncSession):
    group, _, payload = await setup_finish(db)
    await accept_record(db, group, payload, "first")
    second = payload.model_copy(update={"record_uuid": generate_uuid7()})
    result = await accept_record(db, group, second, "second")
    assert result["replay_eligible"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change", [{"bsp_size": 999}, {"mode_version": 1}, {"stage": 7}]
)
async def test_invalid_finish(db: AsyncSession, change):
    group, _, payload = await setup_finish(db)
    result, _ = await check_record(db, group, payload.model_copy(update=change))
    assert not result["eligible"]
    with pytest.raises(HTTPException) as error:
        await accept_record(db, group, payload.model_copy(update=change), "invalid")
    assert error.value.status_code == 422


@pytest.mark.asyncio
async def test_verified_reconciliation_preserves_native_uuid_and_alias(
    db: AsyncSession,
):
    from app.crud.record import get_record_by_uuid, upsert_record
    from app.models import RecordUuidAlias, ServerGlobalapi
    from app.services.record_reconciliation import submit_claim

    group, server, payload = await setup_finish(db, KZMode.KZT)
    result = await accept_record(db, group, payload, "direct")
    upstream_server = ServerGlobalapi(
        id=987654,
        ip=server.ip,
        port=server.port,
        name="upstream",
        group_id=group.id,
        owner_steamid64=group.owner_steamid64,
        approved_by_steamid64=group.owner_steamid64,
    )
    db.add(upstream_server)
    await db.flush()
    mirror, _, _ = await upsert_record(
        session=db,
        record_id=987654,
        record_uuid=generate_uuid7(),
        steamid64=payload.steamid64,
        server_id=upstream_server.id,
        mode_id=payload.mode.mode_id,
        map_id=982345,
        stage=0,
        time_seconds=payload.time,
        teleports=0,
        points=1000,
        created_on=payload.finished_at,
        updated_on=payload.finished_at,
        updated_by=0,
        replay_id=None,
        is_valid=True,
    )
    old = mirror.uuid
    await db.flush()
    response = await submit_claim(
        db, group, uuid.UUID(result["record_uuid"]), mirror.id
    )
    assert response["state"] == "verified"
    alias = await db.get(RecordUuidAlias, old)
    assert alias.record_uuid == payload.record_uuid
    assert (
        await get_record_by_uuid(session=db, record_uuid=old)
    ).uuid == payload.record_uuid


@pytest.mark.asyncio
async def test_replay_upload_is_idempotent_and_listing_uses_catalog(
    db: AsyncSession, monkeypatch
):
    import struct
    from unittest.mock import AsyncMock

    from app.models import RecordReplay, ReplayListQuery
    from app.services import r2_storage
    from app.services.record_replay_catalog import list_replays
    from app.services.record_replay_upload import accept_replay
    from tests.utils.run_replay import build_synthetic_run_replay

    group, _, payload = await setup_finish(db, KZMode.KZT)
    result = await accept_record(db, group, payload, "replay")
    synthetic = build_synthetic_run_replay(
        map_name=payload.map_name,
        tick_count=4518,
        timestamp=int(payload.finished_at.timestamp()),
    )
    ticks = (
        struct.pack("<I", (1 << 20) - 1) + bytes(19 * 4) + struct.pack("<I", 1) * 4517
    )
    data = synthetic.replay_bytes + ticks
    put = AsyncMock(return_value="https://replays.invalid/object")
    monkeypatch.setattr(r2_storage, "put_object", put)
    record_id = uuid.UUID(result["record_uuid"])
    first = await accept_replay(db, group, record_id, data)
    assert await accept_replay(db, group, record_id, data) == first
    assert put.await_count == 1
    entry = await db.get(RecordReplay, record_id)
    assert entry.available and entry.storage == "r2"
    with pytest.raises(HTTPException) as error:
        await accept_replay(db, group, record_id, data + b"x")
    assert error.value.status_code == 409

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Normal catalog reads must not query object storage")

    monkeypatch.setattr(r2_storage, "list_objects", forbidden)
    monkeypatch.setattr("httpx.AsyncClient.head", forbidden)
    ids, count = await list_replays(db, ReplayListQuery())
    assert count == 1 and ids == [record_id]


@pytest.mark.asyncio
async def test_http_auth_ownership_optional_uuid_and_native_reads(db, client):
    group, server, payload = await setup_finish(db)
    body = payload.model_dump(mode="json")
    headers = {"X-Server-Group-Key": group.api_key, "Idempotency-Key": "http-native"}
    assert (await client.post("/v1/records", json=body)).status_code == 401
    assert (
        await client.post(
            "/v1/records", json=body, headers={**headers, "X-Server-Group-Key": "wrong"}
        )
    ).status_code == 401
    other, _ = await create_server_group(db, status=ServerGroupStatus.VALIDATED)
    assert (
        await client.post(
            "/v1/records",
            json=body,
            headers={**headers, "X-Server-Group-Key": other.api_key},
        )
    ).status_code == 403
    assert (
        await client.post(
            "/v1/records",
            json={**body, "record_uuid": str(uuid.uuid4())},
            headers=headers,
        )
    ).status_code == 422
    body.pop("record_uuid")
    response = await client.post("/v1/records", json=body, headers=headers)
    assert response.status_code == 200, response.text
    canonical = response.json()["record_uuid"]
    assert uuid.UUID(canonical).version == 7
    detail = await client.get(f"/v1/records/{canonical}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["native_server_id"] == str(server.id)
    assert detail.json()["server_id"] is None
    assert detail.json()["server_name"] == "Test Server"
    assert detail.json()["server_group"]["id"] == str(group.id)
    recent = await client.get("/v1/records/recent")
    assert recent.status_code == 200, recent.text
    assert any(
        row["uuid"] == canonical and row["server"]["native_id"] == str(server.id)
        for row in recent.json()["data"]
    )


@pytest.mark.asyncio
async def test_bans_integrity_and_group_eligibility(db):
    from app.models import Ban, BanType, Player

    group, _, payload = await setup_finish(db)
    invalid = payload.model_copy(
        update={
            "integrity": payload.integrity.model_copy(update={"anticheat_clear": False})
        }
    )
    with pytest.raises(HTTPException) as error:
        await accept_record(db, group, invalid, "suspected")
    assert error.value.status_code == 422
    group.status = ServerGroupStatus.PENDING
    result, _ = await check_record(db, group, payload)
    assert not result["checks"]["group"]
    group.status = ServerGroupStatus.VALIDATED
    db.add(Player(steamid64=payload.steamid64, name="banned"))
    await db.flush()
    db.add(Ban(steamid64=payload.steamid64, ban_type=BanType.OTHER))
    await db.flush()
    result, _ = await check_record(db, group, payload)
    assert not result["checks"]["player"]


@pytest.mark.asyncio
async def test_verification_outage_and_exact_statistics(db):
    from app.models import RecordSourceClaim, ServerGlobalapi
    from app.services.record_reconciliation import resolve_before_sync, submit_claim

    group, server, payload = await setup_finish(db, KZMode.KZT)
    result = await accept_record(db, group, payload, "pending")
    canonical = uuid.UUID(result["record_uuid"])
    response = await submit_claim(db, group, canonical, 911911)
    assert response["state"] == "pending"
    db.add(
        ServerGlobalapi(
            id=911911,
            ip=server.ip,
            port=server.port,
            name="upstream",
            group_id=group.id,
            owner_steamid64=group.owner_steamid64,
            approved_by_steamid64=group.owner_steamid64,
        )
    )
    await db.flush()
    upstream = Record(
        id=911911,
        steamid64=payload.steamid64,
        server_id=911911,
        mode=payload.mode,
        map_id=982345,
        stage=0,
        time=payload.time,
        teleports=1,
    )
    assert await resolve_before_sync(db, upstream) is None
    upstream.teleports = 0
    assert await resolve_before_sync(db, upstream) == canonical
    claim = (
        await db.exec(
            select(RecordSourceClaim).where(RecordSourceClaim.record_uuid == canonical)
        )
    ).one()
    assert claim.state == "verified" and claim.source_payload["id"] == 911911
    assert (
        len(
            (
                await db.exec(
                    select(Record).where(Record.steamid64 == payload.steamid64)
                )
            ).all()
        )
        == 1
    )


@pytest.mark.asyncio
async def test_write_routes_check_link_and_replay_errors(db, client):
    group, _, payload = await setup_finish(db)
    headers = {"Authorization": f"Bearer {group.api_key}", "Idempotency-Key": "routes"}
    body = payload.model_dump(mode="json")
    check = {
        key: value
        for key, value in body.items()
        if key not in {"record_uuid", "time", "teleports", "finished_at"}
    }
    response = await client.post("/v1/records/check", json=check, headers=headers)
    assert response.status_code == 200 and response.json()["eligible"]
    response = await client.post("/v1/records", json=body, headers=headers)
    canonical = response.json()["record_uuid"]
    link = await client.put(
        f"/v1/records/{canonical}/globalapi",
        json={"globalapi_id": 333444},
        headers=headers,
    )
    assert link.status_code == 200 and link.json()["state"] == "pending"
    replay = await client.put(
        f"/v1/records/{canonical}/replay", content=b"malformed", headers=headers
    )
    assert replay.status_code == 422
    missing = await client.put(
        f"/v1/records/{generate_uuid7()}/replay", content=b"malformed", headers=headers
    )
    assert missing.status_code == 403


@pytest.mark.asyncio
async def test_sync_first_restores_replay_eligibility_and_preserves_moderation(db):
    from app.crud.record import upsert_record
    from app.models import (
        Player,
        RecordSourceClaim,
        RecordUploadReceipt,
        ServerGlobalapi,
    )
    from app.services.record_reconciliation import submit_claim

    group, server, payload = await setup_finish(db, KZMode.KZT)
    db.add(Player(steamid64=payload.steamid64, name="Runner"))
    upstream_server = ServerGlobalapi(
        id=987654,
        ip=server.ip,
        port=server.port,
        name="upstream",
        group_id=group.id,
        owner_steamid64=group.owner_steamid64,
        approved_by_steamid64=group.owner_steamid64,
    )
    db.add(upstream_server)
    await db.flush()
    mirror, _, _ = await upsert_record(
        session=db,
        record_id=987654,
        record_uuid=generate_uuid7(),
        steamid64=payload.steamid64,
        server_id=upstream_server.id,
        mode_id=payload.mode.mode_id,
        map_id=982345,
        stage=0,
        time_seconds=payload.time,
        teleports=0,
        points=1000,
        created_on=payload.finished_at,
        updated_on=payload.finished_at,
        updated_by=0,
        replay_id=None,
        is_valid=True,
    )
    original = mirror.uuid
    mirror.is_valid = False
    db.add(mirror)
    await db.flush()
    result = await accept_record(db, group, payload, "sync-first")
    assert result["replay_eligible"]
    claims = (await db.exec(select(RecordSourceClaim))).all()
    assert len(claims) == 1 and claims[0].state == "verified"
    # Repeated identity claims preserve the moderation decision and receipt.
    response = await submit_claim(db, group, payload.record_uuid, 987654)
    assert response["state"] == "verified"
    assert response["replay_eligible"]
    canonical = await db.get(Record, payload.record_uuid)
    assert not canonical.is_valid
    assert await db.get(Record, original) is None
    receipt = (await db.exec(select(RecordUploadReceipt))).one()
    assert receipt.replay_eligible
    assert claims[0].source_payload["uuid"] == str(original)
    assert await accept_record(db, group, payload, "sync-first") == result


@pytest.mark.asyncio
async def test_replay_storage_failure_keeps_record_and_retries(db, monkeypatch):
    import struct
    from unittest.mock import AsyncMock

    import httpx

    from app.models import RecordReplay
    from app.services import r2_storage
    from app.services.record_replay_upload import accept_replay
    from tests.utils.run_replay import build_synthetic_run_replay

    group, _, payload = await setup_finish(db, KZMode.KZT)
    await accept_record(db, group, payload, "storage-failure")
    synthetic = build_synthetic_run_replay(
        map_name=payload.map_name,
        tick_count=4518,
        timestamp=int(payload.finished_at.timestamp()),
    )
    data = (
        synthetic.replay_bytes
        + struct.pack("<I", (1 << 20) - 1)
        + bytes(76)
        + struct.pack("<I", 1) * 4517
    )
    calls = 0

    async def stored_without_connection(**_kwargs):
        nonlocal calls
        assert not db.in_transaction()
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("offline")

    put = AsyncMock(side_effect=stored_without_connection)
    monkeypatch.setattr(r2_storage, "put_object", put)
    with pytest.raises(HTTPException) as error:
        await accept_replay(db, group, payload.record_uuid, data)
    assert error.value.status_code == 503
    assert error.value.headers["Retry-After"] == "30"
    assert await db.get(Record, payload.record_uuid) is not None
    assert await db.get(RecordReplay, payload.record_uuid) is None
    assert (await accept_replay(db, group, payload.record_uuid, data))["available"]
    assert put.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "submitted_time,accepted",
    [("16.265", True), ("16.266", True), ("16.264", False), ("16.267", False)],
)
async def test_replay_matches_sourcepawn_truncation_or_rounding(
    db, monkeypatch, submitted_time, accepted
):
    import struct
    from unittest.mock import AsyncMock

    from app.services import r2_storage
    from app.services.record_replay_upload import accept_replay
    from tests.utils.run_replay import build_synthetic_run_replay

    group, _, payload = await setup_finish(db, KZMode.KZT)
    payload.time = Decimal(submitted_time)
    await accept_record(db, group, payload, "sourcepawn-time")
    replay = build_synthetic_run_replay(
        map_name=payload.map_name,
        time_seconds=16.265625,
        tick_count=2082,
        timestamp=int(payload.finished_at.timestamp()),
    )
    data = (
        replay.replay_bytes
        + struct.pack("<I", (1 << 20) - 1)
        + bytes(76)
        + struct.pack("<I", 1) * 2081
    )
    put = AsyncMock()
    monkeypatch.setattr(r2_storage, "put_object", put)
    if accepted:
        assert (await accept_replay(db, group, payload.record_uuid, data))["available"]
        put.assert_awaited_once()
    else:
        with pytest.raises(HTTPException) as error:
            await accept_replay(db, group, payload.record_uuid, data)
        assert error.value.status_code == 422
        put.assert_not_awaited()


@pytest.mark.asyncio
async def test_steam_server_identity_uses_existing_server_and_receipt(db):
    group, server, payload = await setup_finish(db, KZMode.KZT)
    server.steamid64 = str((1 << 56) | (3 << 52) | 12345)
    db.add(server)
    await db.flush()
    steam_payload = payload.model_copy(update={"server_id": server.steamid64})
    parsed = RecordFinish.model_validate(steam_payload.model_dump())
    result = await accept_record(db, group, parsed, "steam-finish")
    assert await accept_record(db, group, parsed, "steam-finish") == result
    assert (await db.get(Record, payload.record_uuid)).native_server_id == server.id
    other, _ = await create_server_group(db)
    with pytest.raises(HTTPException) as error:
        await check_record(db, other, parsed)
    assert error.value.status_code == 403
    parsed.server_id = str((1 << 56) | (3 << 52) | 12346)
    with pytest.raises(HTTPException) as error:
        await check_record(db, group, parsed)
    assert error.value.status_code == 503


@pytest.mark.asyncio
@pytest.mark.parametrize("existing", [False, True])
async def test_heartbeat_registers_steam_identity_and_tracks_address(
    db, monkeypatch, existing
):
    from unittest.mock import AsyncMock

    from app.crud.server import upsert_server_from_plugin_heartbeat
    from app.models import ServerStatusPut

    monkeypatch.setattr(
        "app.crud.server._resolve_server_location",
        AsyncMock(return_value=(None, None, None, None)),
    )
    monkeypatch.setattr("app.crud.server._refresh_server_location", AsyncMock())
    group, _ = await create_server_group(db, status=ServerGroupStatus.VALIDATED)
    steamid = str((1 << 56) | (3 << 52) | 13579)
    heartbeat = ServerStatusPut(
        server_steamid64=steamid,
        ip="192.0.2.51",
        port=27015,
        observed_at=get_datetime_utc(),
        hostname="Steam server",
        map="kz_test",
        player_count=0,
        max_players=32,
    )
    previous = (
        await create_server(db, group_id=group.id, ip=heartbeat.ip, port=heartbeat.port)
        if existing
        else None
    )
    server = await upsert_server_from_plugin_heartbeat(
        session=db, group=group, payload=heartbeat
    )
    if previous is not None:
        assert server.id == previous.id
    original = server.id
    assert server.steamid64 == steamid
    heartbeat.ip = "192.0.2.52"
    moved = await upsert_server_from_plugin_heartbeat(
        session=db, group=group, payload=heartbeat
    )
    assert moved.id == original and moved.ip == heartbeat.ip
    other, _ = await create_server_group(db)
    with pytest.raises(ValueError, match="does not belong"):
        await upsert_server_from_plugin_heartbeat(
            session=db, group=other, payload=heartbeat
        )
    from app.models import ServerStatus

    moved.status = ServerStatus.DISABLED
    db.add(moved)
    with pytest.raises(ValueError, match="disabled"):
        await upsert_server_from_plugin_heartbeat(
            session=db, group=group, payload=heartbeat
        )


@pytest.mark.parametrize(
    "identity", ["0", "1", "[I:0:1]", "76561199022242128", "99999999999999999999"]
)
def test_invalid_server_steam_identity_rejected(identity):
    from pydantic import TypeAdapter, ValidationError

    from app.models.server_identity import ServerSteamID

    with pytest.raises(ValidationError):
        TypeAdapter(ServerSteamID).validate_python(identity)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_version,bad_settings", [(False, False), (True, False), (False, True)]
)
async def test_direct_server_status_is_independent_of_globalapi(
    db, bad_version, bad_settings
):
    from app.crud.server import (
        _build_server_live_status_public,
        record_plugin_heartbeat,
    )
    from app.models import ServerStatusPut
    from app.models.server import ServerRecordsStatusPut

    group, server, run = await setup_finish(db, KZMode.NKZ)
    evidence = ServerRecordsStatusPut(
        plugins_valid=True,
        settings_enforcer_valid=not bad_settings,
        bsp_size=run.bsp_size,
        mode_versions={"NKZ": run.mode_version - int(bad_version)},
    )
    payload = ServerStatusPut(
        ip=server.ip,
        port=server.port,
        observed_at=get_datetime_utc(),
        hostname="Direct server",
        map=run.map_name,
        player_count=0,
        max_players=32,
        gokz_top_status=evidence,
    )
    result = await record_plugin_heartbeat(
        session=db, group=group, server=server, payload=payload, notify=False
    )
    public = _build_server_live_status_public(result.live_status)
    assert public.global_status is None
    direct = public.gokz_top_status
    assert direct is not None
    assert direct.modes["NKZ"] is (not bad_version)
    assert direct.modes["KZT"] is False
    assert direct.eligible is (not bad_version and not bad_settings)
    # Older heartbeats must clear readiness rather than retaining stale green state.
    payload.gokz_top_status = None
    result = await record_plugin_heartbeat(
        session=db, group=group, server=server, payload=payload, notify=False
    )
    assert _build_server_live_status_public(result.live_status).gokz_top_status is None


@pytest.mark.asyncio
async def test_direct_finish_refreshes_metadata_and_cached_stats(db: AsyncSession):
    group, _, payload = await setup_finish(db)
    first_at = payload.finished_at - timedelta(days=2)
    player = Player(
        steamid64=payload.steamid64,
        name="Runner",
        alias="Alias",
        country="DE",
        created_at=first_at,
        last_played_at=first_at,
    )
    db.add(player)
    await db.flush()
    for stat_type in PlayerStatType:
        db.add(PlayerStatCache(steamid64=player.steamid64, type=stat_type, content={}))
    await db.flush()
    await accept_record(db, group, payload, "metadata")
    await db.refresh(player)
    assert player.created_at == first_at
    assert player.last_played_at == payload.finished_at
    assert (player.name, player.alias, player.country) == ("Runner", "Alias", "DE")
    caches = (
        await db.exec(
            select(PlayerStatCache).where(PlayerStatCache.steamid64 == player.steamid64)
        )
    ).all()
    assert [row.type for row in caches] == [PlayerStatType.DAILY_ACTIVITY]
    assert caches[0].content["days"][0]["count"] == 1
    # Older queued non-PBs update historical activity without moving Last Played backwards.
    old_at = first_at - timedelta(days=1)
    old = payload.model_copy(
        update={
            "record_uuid": generate_uuid7(),
            "finished_at": old_at,
            "time": Decimal("50.000"),
        }
    )
    result = await accept_record(db, group, old, "old-offline-run")
    await db.refresh(player)
    assert player.created_at == old_at
    assert player.last_played_at == payload.finished_at
    record = await db.get(Record, uuid.UUID(result["record_uuid"]))
    assert record.created_at == old_at
    assert record.updated_at > payload.finished_at
    await accept_record(db, group, old, "old-offline-run")
    await db.refresh(caches[0])
    assert sum(day["count"] for day in caches[0].content["days"]) == 2


@pytest.mark.asyncio
async def test_rejected_finish_does_not_change_player_dates(db: AsyncSession):
    group, _, payload = await setup_finish(db)
    previous = payload.finished_at - timedelta(hours=6)
    player = Player(steamid64=payload.steamid64, name="Runner", last_played_at=previous)
    db.add(player)
    await db.flush()
    with pytest.raises(HTTPException):
        await accept_record(
            db, group, payload.model_copy(update={"bsp_size": 999}), "rejected"
        )
    await db.refresh(player)
    assert player.last_played_at == previous


@pytest.mark.asyncio
async def test_direct_finish_updates_eligible_player_totals(db: AsyncSession):
    from app.models import LeaderboardPlayer

    group, _, payload = await setup_finish(db, KZMode.KZT)
    for index in range(10):
        if index:
            map_obj = Map(
                id=982345 + index,
                name=f"kz_direct_totals_{index}",
                filesize=123,
                validated=True,
            )
            db.add(map_obj)
            await db.flush()
            course = MapCourse(map_id=map_obj.id, stage=0)
            db.add(course)
            await db.flush()
            db.add(MapCourseTier(course_id=course.id, mode=KZMode.KZT, tier=1))
            db.add(
                RecordFilter(
                    id=map_obj.id,
                    map_id=map_obj.id,
                    stage=0,
                    mode=KZMode.KZT,
                    tickrate=128,
                    has_teleports=True,
                )
            )
            await db.flush()
            payload = payload.model_copy(
                update={"map_name": map_obj.name, "record_uuid": generate_uuid7()}
            )
        await accept_record(db, group, payload, f"totals-{index}")
    totals = (
        await db.exec(
            select(LeaderboardPlayer).where(
                LeaderboardPlayer.steamid64 == payload.steamid64
            )
        )
    ).all()
    assert {row.scope for row in totals} == {ModeScope.KZT, ModeScope.OVR}
    for row in totals:
        assert row.unique_map_finishes == 10
        assert row.points == 20000
        assert row.wrs_nub == 10
        assert row.wrs_pro == 10
        assert row.rating > 0


@pytest.mark.asyncio
async def test_repair_existing_native_player_dates(db: AsyncSession):
    from app.record_player_metadata import repair_player_dates

    group, _, payload = await setup_finish(db)
    await accept_record(db, group, payload, "repair")
    player = await db.get(Player, payload.steamid64)
    stale = payload.finished_at - timedelta(hours=6)
    player.last_played_at = stale
    await db.flush()
    selected = await repair_player_dates(db, limit=1, after=0, apply=False)
    assert selected == [player.steamid64]
    await db.refresh(player)
    assert player.last_played_at == stale
    await repair_player_dates(db, limit=1, after=0, apply=True)
    await db.refresh(player)
    assert player.last_played_at == payload.finished_at
    assert (
        await repair_player_dates(db, limit=1, after=player.steamid64, apply=True) == []
    )


@pytest.mark.asyncio
async def test_mirror_identity_refresh_preserves_newer_direct_last_played(
    db: AsyncSession, monkeypatch
):
    from sqlalchemy import text

    from app.services import globalapi_record_sync

    now = get_datetime_utc()
    player = Player(
        steamid64=76561197960278073,
        name="Runner",
        last_played_at=now - timedelta(hours=6),
    )
    db.add(player)
    await db.flush()

    async def steam_lookup(_steamid64):
        # Simulate a direct upload advancing the database while mirror sync is
        # awaiting Steam, leaving its already-loaded Player object stale.
        await db.execute(
            text("UPDATE player SET last_played_at=:now WHERE steamid64=:steam"),
            {"now": now, "steam": player.steamid64},
        )
        return {}

    monkeypatch.setattr(
        globalapi_record_sync.crud, "_fetch_player_from_steam_api", steam_lookup
    )
    result = await globalapi_record_sync._ensure_player(
        session=db,
        steamid64=player.steamid64,
        player_name="Runner",
        created_on=now - timedelta(hours=3),
    )
    assert result.last_played_at == now
