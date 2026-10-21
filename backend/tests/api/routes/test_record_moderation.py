import uuid
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy import event, insert, text
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.api.v1.records import _faster_records_selection
from app.core.config import settings
from app.crud import record as record_crud
from app.models import (
    MapCourse,
    MapLeaderboardCache,
    ModeScope,
    PlayerNotification,
    PlayerNotificationType,
    PlayerReport,
    PlayerStatCache,
    PlayerStatType,
    RecentWrEventCache,
    Record,
    RecordBulkDeleteFaster,
    RecordModerationAction,
    RecordModerationActionRecord,
    RecordModerationActionType,
    RecordPb,
    RecordType,
)
from tests.api.routes.test_records import (
    _create_map,
    _create_record,
    _seed_record_dependencies,
)
from tests.utils.utils import random_steamid64

pytestmark = pytest.mark.asyncio


async def test_faster_preview_selection_can_use_the_map_time_index(
    db: AsyncSession,
) -> None:
    player = random_steamid64()
    await _seed_record_dependencies(db, players=[(player, "Preview Runner")])
    reference = await _create_record(
        db,
        id=None,
        steamid64=player,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="44.055",
        teleports=0,
    )
    _, selection = await _faster_records_selection(
        session=db,
        payload=RecordBulkDeleteFaster(
            record_uuid=reference.uuid,
            scope=ModeScope.OVR,
            type=RecordType.NUB,
        ),
    )
    # Small test tables normally favor sequential scans. Check that the
    # cutoff query is eligible for the ordered partial index at production size.
    await db.exec(text("SET LOCAL enable_seqscan = off"))
    await db.exec(text("SET LOCAL enable_sort = off"))
    connection = await db.connection()
    statement = selection.order_by(Record.time, Record.uuid)
    sql = str(statement.compile(connection, compile_kwargs={"literal_binds": True}))
    plan = (await db.exec(text(f"EXPLAIN (FORMAT JSON) {sql}"))).one()[0]

    def index_names(node: dict[str, Any]) -> set[str]:
        names = {node["Index Name"]} if "Index Name" in node else set()
        for child in node.get("Plans", []):
            names |= index_names(child)
        return names

    assert "ix_record_valid_map_stage_time_uuid" in index_names(plan[0]["Plan"])


@pytest.mark.parametrize(
    "scope,category,reference_mode",
    [
        ("KZT", "NUB", 200),
        ("KZT", "PRO", 200),
        ("OVR", "NUB", 200),
        ("SKZ", "PRO", 201),
        ("VNL", "NUB", 202),
    ],
)
async def test_bulk_faster_scope_history_ties_audit_and_deferred_caches(
    client: AsyncClient,
    db: AsyncSession,
    superuser_token_headers: dict[str, str],
    scope: str,
    category: str,
    reference_mode: int,
) -> None:
    first_player, other_player = random_steamid64(), random_steamid64()
    await _seed_record_dependencies(
        db, players=[(first_player, "First"), (other_player, "Other")]
    )
    await _create_map(db, id=980201, name="kz_other")
    reference = await _create_record(
        db,
        id=None,
        steamid64=first_player,
        server_id=980300,
        mode_id=reference_mode,
        map_id=980200,
        stage=0,
        time="40.001",
        teleports=0,
    )
    specs = [
        (first_player, reference_mode, 980200, 0, "30.000", 0, True),
        (first_player, reference_mode, 980200, 0, "35.000", 0, True),
        (other_player, reference_mode, 980200, 0, "40.000", 0, True),
        (other_player, reference_mode, 980200, 0, "39.000", 2, True),
        (other_player, 203, 980200, 0, "38.000", 0, True),
        (other_player, 201, 980200, 0, "37.000", 0, True),
        (other_player, 202, 980200, 0, "36.000", 0, True),
        (other_player, reference_mode, 980200, 0, "40.001", 0, True),
        (other_player, reference_mode, 980200, 0, "41.000", 0, True),
        (other_player, reference_mode, 980200, 1, "20.000", 0, True),
        (other_player, reference_mode, 980201, 0, "20.000", 0, True),
        (other_player, reference_mode, 980200, 0, "10.000", 0, False),
    ]
    records = [reference]
    for player, mode, map_id, stage, time, teleports, valid in specs:
        records.append(
            await _create_record(
                db,
                id=None,
                steamid64=player,
                server_id=980300,
                mode_id=mode,
                map_id=map_id,
                stage=stage,
                time=time,
                teleports=teleports,
                is_valid=valid,
            )
        )
    allowed_modes = {
        "KZT": {200, 203},
        "OVR": {200, 201, 202, 203},
        "SKZ": {201},
        "VNL": {202},
    }[scope]
    expected = {
        r.uuid
        for r in records
        if r.is_valid
        and r.map_id == 980200
        and r.stage == 0
        and r.mode_id in allowed_modes
        and r.time < reference.time
        and (category == "NUB" or r.teleports == 0)
    }
    payload = {"record_uuid": str(reference.uuid), "scope": scope, "type": category}
    preview = await client.post(
        f"{settings.API_V1_STR}/records/bulk-delete-faster/preview",
        headers=superuser_token_headers,
        json=payload,
    )
    assert preview.status_code == 200, preview.text
    snapshot = preview.json()
    assert snapshot["count"] == len(expected)
    assert len({group["player"]["steamid64"] for group in snapshot["players"]}) == len(
        snapshot["players"]
    )
    assert {
        run["uuid"] for group in snapshot["players"] for run in group["records"]
    } == {str(key) for key in expected}
    assert not (await db.exec(select(RecordModerationAction))).all()
    pbs_before = [pb.model_dump() for pb in (await db.exec(select(RecordPb))).all()]
    caches_before = [
        cache.model_dump()
        for cache in (await db.exec(select(MapLeaderboardCache))).all()
    ]
    wrs_before = [
        wr.model_dump() for wr in (await db.exec(select(RecentWrEventCache))).all()
    ]
    response = await client.post(
        f"{settings.API_V1_STR}/records/bulk-delete-faster",
        headers=superuser_token_headers,
        json=payload | {"preview_token": snapshot["preview_token"]},
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"count": len(expected)}
    for record in records:
        await db.refresh(record)
        assert record.is_valid == (
            record.uuid not in expected and record is not records[-1]
        )
    actions = (await db.exec(select(RecordModerationAction))).all()
    assert len(actions) == 1
    assert actions[0].action_type == RecordModerationActionType.BULK_SOFT_DELETE_FASTER
    assert actions[0].target_record_uuid == reference.uuid
    audit = (await db.exec(select(RecordModerationActionRecord))).all()
    assert {entry.record_uuid for entry in audit} == expected
    assert all(
        entry.before_snapshot["is_valid"] is True
        and entry.after_snapshot["is_valid"] is False
        for entry in audit
    )
    assert [pb.model_dump() for pb in (await db.exec(select(RecordPb))).all()] == [
        pb for pb in pbs_before if pb["record_uuid"] not in expected
    ]
    assert [
        cache.model_dump()
        for cache in (await db.exec(select(MapLeaderboardCache))).all()
    ] == caches_before
    assert [
        wr.model_dump() for wr in (await db.exec(select(RecentWrEventCache))).all()
    ] == wrs_before
    again = await client.post(
        f"{settings.API_V1_STR}/records/bulk-delete-faster",
        headers=superuser_token_headers,
        json=payload,
    )
    assert again.json() == {"count": 0}
    assert len((await db.exec(select(RecordModerationAction))).all()) == 1


async def test_bulk_faster_validation_and_authorization(
    client: AsyncClient,
    db: AsyncSession,
    superuser_token_headers: dict[str, str],
    normal_user_token_headers: dict[str, str],
) -> None:
    player = random_steamid64()
    await _seed_record_dependencies(db, players=[(player, "Runner")])
    reference = await _create_record(
        db,
        id=None,
        steamid64=player,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="40.000",
        teleports=2,
    )
    endpoint = f"{settings.API_V1_STR}/records/bulk-delete-faster"
    payload = {"record_uuid": str(reference.uuid), "scope": "KZT", "type": "NUB"}
    for headers in ({}, normal_user_token_headers):
        response = await client.post(endpoint, headers=headers, json=payload)
        assert response.status_code in (401, 403)
        preview = await client.post(
            endpoint + "/preview", headers=headers, json=payload
        )
        assert preview.status_code in (401, 403)
    for changes, status in [
        ({"record_uuid": str(uuid.uuid7())}, 404),
        ({"scope": "SKZ"}, 422),
        ({"type": "PRO"}, 422),
        ({"scope": "INVALID"}, 422),
    ]:
        response = await client.post(
            endpoint, headers=superuser_token_headers, json=payload | changes
        )
        assert response.status_code == status
        preview = await client.post(
            endpoint + "/preview",
            headers=superuser_token_headers,
            json=payload | changes,
        )
        assert preview.status_code == status
    reference.is_valid = False
    db.add(reference)
    await db.commit()
    response = await client.post(
        endpoint, headers=superuser_token_headers, json=payload
    )
    assert response.status_code == 409
    assert not (await db.exec(select(RecordModerationAction))).all()


@pytest.mark.parametrize("action", ["single", "course", "faster"])
async def test_admin_invalidation_notifies_distinct_reporters_once(
    client: AsyncClient,
    db: AsyncSession,
    superuser_token_headers: dict[str, str],
    action: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target, reporter, second_reporter = [random_steamid64() for _ in range(3)]
    await _seed_record_dependencies(
        db,
        players=[
            (target, "Target"),
            (reporter, "Reporter"),
            (second_reporter, "Second"),
        ],
    )
    record = await _create_record(
        db,
        id=None,
        steamid64=target,
        server_id=980300,
        mode_id=203,
        map_id=980200,
        stage=0,
        time="30.000",
        teleports=0,
    )
    reference = await _create_record(
        db,
        id=None,
        steamid64=reporter,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="40.000",
        teleports=0,
    )
    for who, record_uuid in [
        (reporter, record.uuid),
        (reporter, record.uuid),
        (second_reporter, record.uuid),
        (second_reporter, reference.uuid),
        (reporter, None),
    ]:
        db.add(
            PlayerReport(
                reporter_steamid64=who,
                target_steamid64=target if record_uuid != reference.uuid else reporter,
                record_uuid=record_uuid,
            )
        )
    await db.commit()
    refreshes = [
        AsyncMock(wraps=getattr(record_crud, name))
        for name in (
            "_refresh_record_read_models_for_change",
            "rebuild_record_pb_buckets_for_keys",
            "rebuild_map_leaderboards_for_keys",
            "refresh_player_daily_activity_cache_dates",
        )
    ]
    for name, refresh in zip(
        (
            "_refresh_record_read_models_for_change",
            "rebuild_record_pb_buckets_for_keys",
            "rebuild_map_leaderboards_for_keys",
            "refresh_player_daily_activity_cache_dates",
        ),
        refreshes,
        strict=True,
    ):
        monkeypatch.setattr(record_crud, name, refresh)
    if action == "single":
        response = await client.patch(
            f"{settings.API_V1_STR}/records/{record.uuid}",
            headers=superuser_token_headers,
            json={"is_valid": False},
        )
    else:
        suffix = "bulk-delete-course" if action == "course" else "bulk-delete-faster"
        payload = (
            {"steamid64": str(target), "map_id": 980200, "stage": 0}
            if action == "course"
            else {"record_uuid": str(reference.uuid), "scope": "KZT", "type": "PRO"}
        )
        response = await client.post(
            f"{settings.API_V1_STR}/records/{suffix}",
            headers=superuser_token_headers,
            json=payload,
        )
    assert response.status_code == 200, response.text
    notifications = (
        await db.exec(
            select(PlayerNotification).where(
                PlayerNotification.type
                == PlayerNotificationType.REPORTED_RECORD_INVALIDATED
            )
        )
    ).all()
    assert {n.recipient_steamid64 for n in notifications} == {reporter, second_reporter}
    assert len(notifications) == 2
    assert all(
        n.new_record_uuid == record.uuid
        and n.new_record_time == 30
        and n.map_name == "kz_record_test"
        and n.target_player_steamid64 == target
        and n.read_at is None
        for n in notifications
    )
    for refresh in refreshes:
        refresh.assert_not_awaited()
    monkeypatch.undo()
    for valid in (False, True, False):
        response = await client.patch(
            f"{settings.API_V1_STR}/records/{record.uuid}",
            headers=superuser_token_headers,
            json={"is_valid": valid},
        )
        assert response.status_code == 200
    assert len((await db.exec(select(PlayerNotification))).all()) == 2


async def test_invalidation_rolls_back_when_notification_creation_fails(
    client: AsyncClient,
    db: AsyncSession,
    superuser_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    player = random_steamid64()
    await _seed_record_dependencies(db, players=[(player, "Runner")])
    record = await _create_record(
        db,
        id=None,
        steamid64=player,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="30.000",
        teleports=0,
    )
    record_uuid = record.uuid
    monkeypatch.setattr(
        record_crud,
        "create_reported_record_invalidated_notifications",
        AsyncMock(side_effect=RuntimeError("notification failed")),
    )
    with pytest.raises(RuntimeError, match="notification failed"):
        async with db.begin_nested():
            await client.post(
                f"{settings.API_V1_STR}/records/bulk-delete-course",
                headers=superuser_token_headers,
                json={"steamid64": str(player), "map_id": 980200, "stage": 0},
            )
    await db.refresh(record)
    assert record.is_valid
    assert not (await db.exec(select(RecordModerationAction))).all()
    assert (
        await db.exec(select(RecordPb).where(RecordPb.record_uuid == record_uuid))
    ).all()


async def test_sync_invalidation_does_not_notify_reporter(db: AsyncSession) -> None:
    target, reporter = random_steamid64(), random_steamid64()
    await _seed_record_dependencies(
        db, players=[(target, "Target"), (reporter, "Reporter")]
    )
    record = await _create_record(
        db,
        id=989901,
        steamid64=target,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="30.000",
        teleports=0,
    )
    db.add(
        PlayerReport(
            reporter_steamid64=reporter,
            target_steamid64=target,
            record_uuid=record.uuid,
        )
    )
    await db.commit()
    await crud.upsert_record(
        session=db,
        record_id=record.id,
        record_uuid=None,
        steamid64=target,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time_seconds=Decimal("30.000"),
        teleports=0,
        points=0,
        created_on=record.created_at,
        updated_on=record.updated_at,
        updated_by=target,
        replay_id=None,
        is_valid=False,
    )
    await db.commit()
    assert not (await db.exec(select(PlayerNotification))).all()


async def test_faster_bonus_preserves_main_world_record(
    client: AsyncClient,
    db: AsyncSession,
    superuser_token_headers: dict[str, str],
) -> None:
    player = random_steamid64()
    await _seed_record_dependencies(db, players=[(player, "Bonus Runner")])
    runs = []
    for stage, time in [(0, "10.000"), (1, "20.000"), (1, "30.000")]:
        runs.append(
            await _create_record(
                db,
                id=None,
                steamid64=player,
                server_id=980300,
                mode_id=200,
                map_id=980200,
                stage=stage,
                time=time,
                teleports=0,
            )
        )
    reference = runs[-1]
    response = await client.post(
        f"{settings.API_V1_STR}/records/bulk-delete-faster",
        headers=superuser_token_headers,
        json={"record_uuid": str(reference.uuid), "scope": "KZT", "type": "PRO"},
    )
    assert response.status_code == 200
    assert response.json() == {"count": 1}
    await db.refresh(runs[0])
    assert runs[0].is_valid
    wrs = await crud.read_map_wrs(
        session=db, map_id=980200, scope=ModeScope.KZT, record_type=RecordType.PRO
    )
    assert wrs[0].record_uuid == runs[0].uuid
    course = (
        await db.exec(
            select(MapCourse).where(MapCourse.map_id == 980200, MapCourse.stage == 1)
        )
    ).one()
    pb = await db.get(RecordPb, (ModeScope.KZT, course.id, player, RecordType.PRO))
    assert pb is None


@pytest.mark.parametrize("change", ["add", "update"])
async def test_faster_preview_requires_review_when_records_change(
    client: AsyncClient,
    db: AsyncSession,
    superuser_token_headers: dict[str, str],
    change: str,
) -> None:
    player = random_steamid64()
    await _seed_record_dependencies(db, players=[(player, "Preview Runner")])
    reference = await _create_record(
        db,
        id=None,
        steamid64=player,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="40.000",
        teleports=0,
    )
    faster = await _create_record(
        db,
        id=None,
        steamid64=player,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="30.000",
        teleports=0,
    )
    endpoint = f"{settings.API_V1_STR}/records/bulk-delete-faster"
    payload = {"record_uuid": str(reference.uuid), "scope": "OVR", "type": "NUB"}
    response = await client.post(
        endpoint + "/preview", headers=superuser_token_headers, json=payload
    )
    preview = response.json()
    assert preview["count"] == 1
    assert len(preview["players"]) == 1
    assert preview["players"][0]["records"][0]["server_name"] == "Record Test Server"
    if change == "add":
        await _create_record(
            db,
            id=None,
            steamid64=player,
            server_id=980300,
            mode_id=203,
            map_id=980200,
            stage=0,
            time="20.000",
            teleports=2,
        )
    else:
        faster.time = Decimal("31.000")
        db.add(faster)
        await db.commit()
    rejected = await client.post(
        endpoint,
        headers=superuser_token_headers,
        json=payload | {"preview_token": preview["preview_token"]},
    )
    assert rejected.status_code == 409
    await db.refresh(faster)
    assert faster.is_valid
    assert not (await db.exec(select(RecordModerationAction))).all()
    refreshed = await client.post(
        endpoint + "/preview", headers=superuser_token_headers, json=payload
    )
    new_preview = refreshed.json()
    assert new_preview["preview_token"] != preview["preview_token"]
    deleted = await client.post(
        endpoint,
        headers=superuser_token_headers,
        json=payload | {"preview_token": new_preview["preview_token"]},
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["count"] == new_preview["count"]
    empty = await client.post(
        endpoint + "/preview", headers=superuser_token_headers, json=payload
    )
    assert empty.json()["count"] == 0
    assert empty.json()["players"] == []


async def test_bulk_invalidation_batches_audits_and_notifications_without_cache_work(
    db: AsyncSession,
) -> None:
    target, reporter = random_steamid64(), random_steamid64()
    await _seed_record_dependencies(
        db, players=[(target, "Runner"), (reporter, "Reporter")]
    )
    records = [
        Record(
            steamid64=target,
            server_id=980300,
            mode_id=200,
            map_id=980200,
            time=Decimal("20") + Decimal(index) / 1000,
        )
        for index in range(1001)
    ]
    await db.execute(insert(Record), [record.model_dump() for record in records])
    course = MapCourse(map_id=980200, stage=0)
    db.add(course)
    await db.flush()
    assert course.id is not None
    db.add_all(
        [
            RecordPb(
                scope=scope,
                course_id=course.id,
                steamid64=target,
                type=category,
                record_uuid=records[0].uuid,
                time=records[0].time,
                points=1000,
            )
            for scope in (ModeScope.OVR, ModeScope.KZT)
            for category in RecordType
        ]
    )
    reports = [
        PlayerReport(
            reporter_steamid64=reporter,
            target_steamid64=target,
            record_uuid=record.uuid,
        ).model_dump()
        for record in records
    ]
    await db.execute(insert(PlayerReport), reports)
    db.add(
        PlayerReport(
            reporter_steamid64=reporter,
            target_steamid64=target,
            record_uuid=records[0].uuid,
        )
    )
    content = {
        "days": [{"date": records[0].created_at.date().isoformat(), "count": 1001}]
    }
    activity_cache = PlayerStatCache(
        steamid64=target,
        type=PlayerStatType.DAILY_ACTIVITY,
        content=content,
    )
    db.add(activity_cache)
    await db.commit()
    cached_at = activity_cache.updated_at
    loaded_records = list(
        (
            await db.exec(
                select(Record).where(Record.steamid64 == target).with_for_update()
            )
        ).all()
    )
    statements: list[str] = []

    def capture_sql(
        _connection: Any,
        _cursor: Any,
        statement: str,
        _parameters: Any,
        _context: Any,
        _executemany: bool,
    ) -> None:
        statements.append(statement)

    connection = await db.connection()
    event.listen(connection.sync_connection, "before_cursor_execute", capture_sql)
    try:
        await record_crud.soft_delete_records_with_audit(
            session=db,
            records=loaded_records,
            action=RecordModerationAction(
                actor_steamid64=reporter,
                action_type=RecordModerationActionType.BULK_SOFT_DELETE_FASTER,
                target_map_id=980200,
                target_stage=0,
            ),
        )
    finally:
        event.remove(connection.sync_connection, "before_cursor_execute", capture_sql)
    # The request scales by insert batches, not by records or reporters.
    assert len(statements) < 20
    assert not any("cache." in statement for statement in statements)
    assert all(not record.is_valid for record in loaded_records)
    await db.refresh(loaded_records[-1])
    assert not loaded_records[-1].is_valid
    assert not (await db.exec(select(RecordPb))).all()
    audits = (await db.exec(select(RecordModerationActionRecord))).all()
    assert {audit.record_uuid for audit in audits} == {
        record.uuid for record in records
    }
    assert all(
        audit.before_snapshot["is_valid"] is True
        and audit.after_snapshot["is_valid"] is False
        for audit in audits
    )
    notifications = (await db.exec(select(PlayerNotification))).all()
    assert len(notifications) == 1001
    assert {notice.new_record_uuid for notice in notifications} == {
        record.uuid for record in records
    }
    await db.refresh(activity_cache)
    assert activity_cache.content == content
    assert activity_cache.updated_at == cached_at
