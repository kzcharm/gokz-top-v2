import uuid
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
    Record,
    ServerGroupStatus,
    generate_uuid7,
    get_datetime_utc,
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
    from app.models import ServerGlobalapi, RecordUuidAlias
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

    def forbidden(*args, **kwargs):
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
    from app.services.record_reconciliation import submit_claim, resolve_before_sync

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
    result = await accept_record(db, group, payload, "sync-first")
    assert not result["replay_eligible"]
    claims = (await db.exec(select(RecordSourceClaim))).all()
    assert len(claims) == 1 and claims[0].state == "review"
    # A moderation decision made between ingestion and reconciliation must survive.
    mirror.is_valid = False
    db.add(mirror)
    await db.flush()
    response = await submit_claim(db, group, payload.record_uuid, mirror.id)
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
    import httpx
    from unittest.mock import AsyncMock
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
    put = AsyncMock(side_effect=[httpx.ConnectError("offline"), None])
    monkeypatch.setattr(r2_storage, "put_object", put)
    with pytest.raises(HTTPException) as error:
        await accept_replay(db, group, payload.record_uuid, data)
    assert error.value.status_code == 503
    assert error.value.headers["Retry-After"] == "30"
    assert await db.get(Record, payload.record_uuid) is not None
    assert await db.get(RecordReplay, payload.record_uuid) is None
    assert (await accept_replay(db, group, payload.record_uuid, data))["available"]
    assert put.await_count == 2
