from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.models import (
    Map,
    MapCourse,
    Player,
    Record,
    RecordFilter,
    RecordPb,
    RecordScope,
    RecordType,
    ServerGlobalapi,
)
from tests.utils.utils import random_steamid64

pytestmark = pytest.mark.asyncio


async def _create_player(db: AsyncSession, *, steamid64: int, name: str) -> None:
    await db.exec(delete(Player).where(Player.steamid64 == steamid64))
    await db.commit()
    db.add(Player(steamid64=steamid64, name=name))
    await db.commit()


async def _create_map(
    db: AsyncSession,
    *,
    id: int,
    name: str,
    validated: bool = True,
    difficulty: int = 1,
) -> None:
    await db.exec(delete(Map).where(Map.id == id))
    await db.commit()
    db.add(
        Map(
            id=id,
            name=name,
            filesize=1,
            validated=validated,
            difficulty=difficulty,
            approved_by_steamid64=76561198003275951,
        )
    )
    await db.commit()


async def _create_server(db: AsyncSession, *, id: int, name: str) -> None:
    await db.exec(delete(ServerGlobalapi).where(ServerGlobalapi.id == id))
    await db.commit()
    db.add(
        ServerGlobalapi(
            id=id,
            port=27015,
            ip=f"203.0.113.{id % 255}",
            name=name,
            owner_steamid64=76561198000000010,
            approval_status=1,
            approved_by_steamid64=76561198000000020,
        )
    )
    await db.commit()


async def _create_record_filter(
    db: AsyncSession,
    *,
    id: int,
    map_id: int,
    stage: int,
    mode_id: int,
    tier: int | None,
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
            tier=tier,
            updated_by_id="0",
        )
    )
    await db.commit()


async def _create_record(
    db: AsyncSession,
    *,
    id: int | None,
    steamid64: int,
    map_id: int,
    server_id: int,
    mode_id: int,
    stage: int,
    time: str,
    teleports: int,
) -> Record:
    if id is not None:
        record_uuid_subquery = select(Record.uuid).where(Record.id == id)
        await db.exec(
            delete(RecordPb).where(RecordPb.record_uuid.in_(record_uuid_subquery))
        )
        await db.exec(delete(Record).where(Record.id == id))
        await db.commit()
    record, _created, _updated = await crud.upsert_record(
        session=db,
        record_id=id,
        record_uuid=None,
        steamid64=steamid64,
        server_id=server_id,
        mode_id=mode_id,
        map_id=map_id,
        stage=stage,
        time_seconds=Decimal(time),
        teleports=teleports,
        points=0,
        created_on=datetime(2026, 1, 1, tzinfo=UTC),
        updated_on=datetime(2026, 1, 1, tzinfo=UTC),
        updated_by=steamid64,
        replay_id=None,
        is_valid=True,
    )
    await db.commit()
    await db.refresh(record)
    return record


async def test_get_pb_records_tie_break_prefers_lower_globalapi_id(
    db: AsyncSession,
) -> None:
    player_id = random_steamid64()
    await _create_player(db, steamid64=player_id, name="Tie Runner")
    await _create_map(db, id=981000, name="kz_tie_break")
    await _create_server(db, id=981100, name="Tie Server")

    winner = await _create_record(
        db,
        id=981200,
        steamid64=player_id,
        map_id=981000,
        server_id=981100,
        mode_id=200,
        stage=0,
        time="12.345",
        teleports=0,
    )
    await _create_record(
        db,
        id=981201,
        steamid64=player_id,
        map_id=981000,
        server_id=981100,
        mode_id=201,
        stage=0,
        time="12.345",
        teleports=0,
    )

    records = await crud.get_pb_records(
        db,
        map_id=981000,
        stage=0,
        steamid64=None,
        scope=RecordScope.OVR,
        record_type=RecordType.NUB,
    )

    assert [record.id for record in records] == [winner.id]


async def test_get_max_record_globalapi_id_ignores_null_ids(
    db: AsyncSession,
) -> None:
    player_id = random_steamid64()
    await _create_player(db, steamid64=player_id, name="Max Runner")
    await _create_map(db, id=981001, name="kz_max_id")
    await _create_server(db, id=981101, name="Max Server")

    await _create_record(
        db,
        id=981210,
        steamid64=player_id,
        map_id=981001,
        server_id=981101,
        mode_id=200,
        stage=0,
        time="20.000",
        teleports=0,
    )
    await _create_record(
        db,
        id=None,
        steamid64=player_id,
        map_id=981001,
        server_id=981101,
        mode_id=200,
        stage=1,
        time="21.000",
        teleports=0,
    )

    assert await crud.get_max_record_globalapi_id(session=db) == 981210


async def test_get_pb_records_player_anchor_respects_stage_filter(
    db: AsyncSession,
) -> None:
    player_id = random_steamid64()
    await _create_player(db, steamid64=player_id, name="Stage Runner")
    await _create_map(db, id=981004, name="kz_stage_main")
    await _create_map(db, id=981005, name="kz_stage_bonus")
    await _create_server(db, id=981102, name="Stage Server")

    main_record = await _create_record(
        db,
        id=981230,
        steamid64=player_id,
        map_id=981004,
        server_id=981102,
        mode_id=200,
        stage=0,
        time="20.000",
        teleports=0,
    )
    bonus_record = await _create_record(
        db,
        id=981231,
        steamid64=player_id,
        map_id=981005,
        server_id=981102,
        mode_id=201,
        stage=1,
        time="30.000",
        teleports=0,
    )

    main_records = await crud.get_pb_records(
        db,
        map_id=None,
        stage=0,
        steamid64=player_id,
        scope=RecordScope.OVR,
        record_type=RecordType.PRO,
    )
    bonus_records = await crud.get_pb_records(
        db,
        map_id=None,
        stage=1,
        steamid64=player_id,
        scope=RecordScope.OVR,
        record_type=RecordType.PRO,
    )

    assert [record.id for record in main_records] == [main_record.id]
    assert [record.id for record in bonus_records] == [bonus_record.id]


async def test_load_scoped_course_tiers_uses_scope_min_and_stage_fallbacks(
    db: AsyncSession,
) -> None:
    await _create_map(db, id=981002, name="kz_tier_scope")
    await _create_map(db, id=981003, name="kz_tier_bonus")
    await _create_record_filter(
        db,
        id=981300,
        map_id=981002,
        stage=0,
        mode_id=200,
        tier=6,
    )
    await _create_record_filter(
        db,
        id=981301,
        map_id=981002,
        stage=0,
        mode_id=201,
        tier=2,
    )
    await _create_record_filter(
        db,
        id=981302,
        map_id=981003,
        stage=1,
        mode_id=201,
        tier=5,
    )

    tiers = await crud.load_scoped_course_tiers(
        session=db,
        course_keys=[(981002, 0), (981003, 1), (981003, 2)],
        scope=RecordScope.OVR,
    )

    assert tiers[(981002, 0)] == 2
    assert tiers[(981003, 1)] == 5
    assert tiers[(981003, 2)] == 0


async def test_load_map_tiers_by_scope_uses_scope_min_and_main_fallbacks(
    db: AsyncSession,
) -> None:
    await _create_map(db, id=981006, name="kz_map_tiers")
    await _create_map(db, id=981007, name="kz_map_tiers_fallback")
    await _create_record_filter(
        db,
        id=981303,
        map_id=981006,
        stage=0,
        mode_id=200,
        tier=6,
    )
    await _create_record_filter(
        db,
        id=981304,
        map_id=981006,
        stage=0,
        mode_id=201,
        tier=2,
    )
    await _create_record_filter(
        db,
        id=981305,
        map_id=981006,
        stage=0,
        mode_id=202,
        tier=8,
    )

    tiers_by_map_id = await crud.load_map_tiers_by_scope(
        session=db,
        map_ids=[981006, 981007],
    )

    assert tiers_by_map_id[981006].model_dump() == {
        "OVR": 2,
        "KZT": 6,
        "SKZ": 2,
        "VNL": 8,
    }
    assert tiers_by_map_id[981007].model_dump() == {
        "OVR": 1,
        "KZT": 1,
        "SKZ": 1,
        "VNL": 1,
    }


async def test_get_recent_record_public_by_uuid_uses_bonus_fallback_zero(
    db: AsyncSession,
) -> None:
    player_id = random_steamid64()
    map_id = 1_998_201
    server_id = 1_998_301
    await _create_player(db, steamid64=player_id, name="Recent Runner")
    await _create_map(db, id=map_id, name="kz_recent_scope")
    await _create_server(db, id=server_id, name="Recent Server")

    record = await _create_record(
        db,
        id=981220,
        steamid64=player_id,
        map_id=map_id,
        server_id=server_id,
        mode_id=200,
        stage=2,
        time="45.000",
        teleports=1,
    )

    recent_record = await crud.get_recent_record_public_by_uuid(
        session=db,
        record_uuid=record.uuid,
        scope=RecordScope.OVR,
    )

    assert recent_record is not None
    assert recent_record.map.tier == 0


async def test_rebuild_record_pb_points_bucket_updates_real_points(
    db: AsyncSession,
) -> None:
    first_player = random_steamid64()
    second_player = random_steamid64()
    await _create_player(db, steamid64=first_player, name="Bucket One")
    await _create_player(db, steamid64=second_player, name="Bucket Two")
    await _create_map(db, id=981020, name="kz_bucket_points", difficulty=4)
    await _create_server(db, id=981120, name="Bucket Server")

    await _create_record(
        db,
        id=981320,
        steamid64=first_player,
        map_id=981020,
        server_id=981120,
        mode_id=200,
        stage=0,
        time="10.000",
        teleports=1,
    )
    await _create_record(
        db,
        id=981321,
        steamid64=second_player,
        map_id=981020,
        server_id=981120,
        mode_id=200,
        stage=0,
        time="12.000",
        teleports=1,
    )

    course = (
        await db.exec(
            select(MapCourse).where(MapCourse.map_id == 981020, MapCourse.stage == 0)
        )
    ).one()
    bucket_rows = (
        await db.exec(
            select(RecordPb).where(
                RecordPb.course_id == course.id,
                RecordPb.scope == 0,
                RecordPb.is_pro_only.is_(False),
            )
        )
    ).all()
    original_updated_on = datetime(2026, 2, 1, tzinfo=UTC)
    for row in bucket_rows:
        row.points = 1
        row.updated_at = original_updated_on
        db.add(row)
    await db.commit()

    updated_rows = await crud.rebuild_record_pb_points_bucket(
        session=db,
        course_id=course.id,
        scope_id=0,
        record_type=RecordType.NUB,
    )
    await db.commit()

    refreshed_rows = (
        await db.exec(
            select(RecordPb)
            .where(
                RecordPb.course_id == course.id,
                RecordPb.scope == 0,
                RecordPb.is_pro_only.is_(False),
            )
            .order_by(RecordPb.time_ms.asc())
        )
    ).all()
    assert updated_rows == 2
    assert refreshed_rows[0].points == 1000
    assert refreshed_rows[1].points > 1
    assert refreshed_rows[0].updated_at == original_updated_on
    assert refreshed_rows[1].updated_at == original_updated_on


async def test_rebuild_record_pb_points_for_course_updates_all_selected_buckets(
    db: AsyncSession,
) -> None:
    first_player = random_steamid64()
    second_player = random_steamid64()
    await _create_player(db, steamid64=first_player, name="Course One")
    await _create_player(db, steamid64=second_player, name="Course Two")
    await _create_map(db, id=981024, name="kz_course_points", difficulty=4)
    await _create_server(db, id=981124, name="Course Server")

    await _create_record(
        db,
        id=981322,
        steamid64=first_player,
        map_id=981024,
        server_id=981124,
        mode_id=200,
        stage=0,
        time="10.000",
        teleports=0,
    )
    await _create_record(
        db,
        id=981323,
        steamid64=second_player,
        map_id=981024,
        server_id=981124,
        mode_id=200,
        stage=0,
        time="12.000",
        teleports=1,
    )

    course = (
        await db.exec(
            select(MapCourse).where(MapCourse.map_id == 981024, MapCourse.stage == 0)
        )
    ).one()
    bucket_rows = (
        await db.exec(
            select(RecordPb).where(
                RecordPb.course_id == course.id,
                RecordPb.scope.in_([0, 1]),
            )
        )
    ).all()
    original_updated_on = datetime(2026, 2, 2, tzinfo=UTC)
    for row in bucket_rows:
        row.points = 1
        row.updated_at = original_updated_on
        db.add(row)
    await db.commit()

    updated_rows = await crud.rebuild_record_pb_points_for_course(
        session=db,
        course_id=course.id,
        scope_ids=[0, 1],
        tiers_by_scope={0: 4, 1: 4},
    )
    await db.commit()

    refreshed_rows = (
        await db.exec(
            select(RecordPb)
            .where(
                RecordPb.course_id == course.id,
                RecordPb.scope.in_([0, 1]),
            )
            .order_by(
                RecordPb.scope.asc(),
                RecordPb.is_pro_only.asc(),
                RecordPb.time_ms.asc(),
            )
        )
    ).all()

    assert updated_rows == 6
    assert len(refreshed_rows) == 6
    assert refreshed_rows[0].points == 1000
    assert refreshed_rows[1].points > 1
    assert refreshed_rows[2].points == 1000
    assert refreshed_rows[3].points == 1000
    assert refreshed_rows[4].points > 1
    assert refreshed_rows[5].points == 1000
    assert all(row.updated_at == original_updated_on for row in refreshed_rows)


async def test_record_pb_updated_at_uses_record_created_at_for_new_rows_and_now_for_winner_changes(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    player_id = random_steamid64()
    await _create_player(db, steamid64=player_id, name="PB Winner")
    await _create_map(db, id=981025, name="kz_pb_updated_on", difficulty=4)
    await _create_server(db, id=981125, name="PB Update Server")

    initial_updated_on = datetime(2026, 3, 1, tzinfo=UTC)
    monkeypatch.setattr(crud.record, "get_datetime_utc", lambda: initial_updated_on)
    first_record = await _create_record(
        db,
        id=981324,
        steamid64=player_id,
        map_id=981025,
        server_id=981125,
        mode_id=200,
        stage=0,
        time="12.000",
        teleports=1,
    )

    course = (
        await db.exec(
            select(MapCourse).where(MapCourse.map_id == 981025, MapCourse.stage == 0)
        )
    ).one()
    initial_pb = (
        await db.exec(
            select(RecordPb).where(
                RecordPb.course_id == course.id,
                RecordPb.scope == 0,
                RecordPb.steamid64 == player_id,
                RecordPb.is_pro_only.is_(False),
            )
        )
    ).one()

    assert initial_pb.record_uuid == first_record.uuid
    assert initial_pb.updated_at == datetime(2026, 1, 1, tzinfo=UTC)

    next_updated_on = datetime(2026, 3, 2, tzinfo=UTC)
    monkeypatch.setattr(crud.record, "get_datetime_utc", lambda: next_updated_on)
    second_record = await _create_record(
        db,
        id=981325,
        steamid64=player_id,
        map_id=981025,
        server_id=981125,
        mode_id=200,
        stage=0,
        time="11.000",
        teleports=1,
    )

    refreshed_pb = (
        await db.exec(
            select(RecordPb).where(
                RecordPb.course_id == course.id,
                RecordPb.scope == 0,
                RecordPb.steamid64 == player_id,
                RecordPb.is_pro_only.is_(False),
            )
        )
    ).one()

    assert refreshed_pb.record_uuid == second_record.uuid
    assert refreshed_pb.record_uuid != first_record.uuid
    assert refreshed_pb.updated_at == next_updated_on


async def test_upsert_record_sets_estimated_points_for_new_pb_rows(
    db: AsyncSession,
) -> None:
    first_player = random_steamid64()
    second_player = random_steamid64()
    await _create_player(db, steamid64=first_player, name="Estimate One")
    await _create_player(db, steamid64=second_player, name="Estimate Two")
    await _create_map(db, id=981021, name="kz_estimate_points", difficulty=4)
    await _create_server(db, id=981121, name="Estimate Server")

    first_record, _, _ = await crud.upsert_record(
        session=db,
        record_id=981330,
        record_uuid=None,
        steamid64=first_player,
        server_id=981121,
        mode_id=200,
        map_id=981021,
        stage=0,
        time_seconds=Decimal("10.000"),
        teleports=1,
        points=0,
        created_on=datetime(2026, 1, 1, tzinfo=UTC),
        updated_on=datetime(2026, 1, 1, tzinfo=UTC),
        updated_by=first_player,
        replay_id=None,
        is_valid=True,
    )
    await db.commit()

    second_record, _, _ = await crud.upsert_record(
        session=db,
        record_id=981331,
        record_uuid=None,
        steamid64=second_player,
        server_id=981121,
        mode_id=200,
        map_id=981021,
        stage=0,
        time_seconds=Decimal("12.000"),
        teleports=1,
        points=0,
        created_on=datetime(2026, 1, 2, tzinfo=UTC),
        updated_on=datetime(2026, 1, 2, tzinfo=UTC),
        updated_by=second_player,
        replay_id=None,
        is_valid=True,
    )
    await db.commit()

    points_by_uuid = await crud.load_scoped_points_by_record_uuid(
        session=db,
        record_uuids=[first_record.uuid, second_record.uuid],
        scope=RecordScope.OVR,
    )

    assert points_by_uuid[first_record.uuid] == 1000
    assert points_by_uuid[second_record.uuid] > 1


async def test_rebuild_record_pbs_for_course_skips_unvalidated_maps(
    db: AsyncSession,
) -> None:
    player_id = random_steamid64()
    await _create_player(db, steamid64=player_id, name="Invalid Map Runner")
    await _create_map(
        db,
        id=981022,
        name="kz_invalid_map",
        validated=False,
        difficulty=4,
    )
    await _create_server(db, id=981122, name="Invalid Map Server")

    record = Record(
        id=981340,
        steamid64=player_id,
        server_id=981122,
        mode_id=200,
        map_id=981022,
        stage=0,
        time=Decimal("15.000"),
        teleports=1,
        created_on=datetime(2026, 1, 1, tzinfo=UTC),
        updated_on=datetime(2026, 1, 1, tzinfo=UTC),
        updated_by=player_id,
        is_valid=True,
    )
    db.add(record)
    await db.commit()
    await crud.ensure_map_courses_for_valid_records(session=db)

    course = (
        await db.exec(
            select(MapCourse).where(MapCourse.map_id == 981022, MapCourse.stage == 0)
        )
    ).one()
    await crud.rebuild_record_pbs_for_course(
        session=db,
        course_id=course.id,
        map_id=981022,
        stage=0,
    )
    await db.commit()

    assert (
        await db.exec(select(RecordPb).where(RecordPb.course_id == course.id))
    ).all() == []


async def test_rebuild_record_pbs_for_course_keeps_bonus_points_for_validated_maps(
    db: AsyncSession,
) -> None:
    player_id = random_steamid64()
    await _create_player(db, steamid64=player_id, name="Bonus Points Runner")
    await _create_map(db, id=981023, name="kz_bonus_points", difficulty=5)
    await _create_server(db, id=981123, name="Bonus Points Server")

    bonus_record = await _create_record(
        db,
        id=981350,
        steamid64=player_id,
        map_id=981023,
        server_id=981123,
        mode_id=200,
        stage=1,
        time="25.000",
        teleports=1,
    )

    points_by_uuid = await crud.load_scoped_points_by_record_uuid(
        session=db,
        record_uuids=[bonus_record.uuid],
        scope=RecordScope.OVR,
    )

    assert points_by_uuid[bonus_record.uuid] == 1000


async def test_read_map_wrs_uses_record_pb_main_course_rows(
    db: AsyncSession,
) -> None:
    nub_player = random_steamid64()
    pro_player = random_steamid64()
    await _create_player(db, steamid64=nub_player, name="Nub WR")
    await _create_player(db, steamid64=pro_player, name="Pro WR")
    await _create_map(db, id=981024, name="kz_map_wr_pb_source")
    await _create_server(db, id=981124, name="Map WR Server")

    nub_record = await _create_record(
        db,
        id=981360,
        steamid64=nub_player,
        map_id=981024,
        server_id=981124,
        mode_id=200,
        stage=0,
        time="10.000",
        teleports=1,
    )
    pro_record = await _create_record(
        db,
        id=981361,
        steamid64=pro_player,
        map_id=981024,
        server_id=981124,
        mode_id=200,
        stage=0,
        time="11.000",
        teleports=0,
    )

    wr_rows = await crud.read_map_wrs(
        session=db,
        map_id=981024,
        scope=RecordScope.OVR,
    )
    assert [(row.type, row.record_uuid) for row in wr_rows] == [
        (RecordType.NUB, nub_record.uuid),
        (RecordType.PRO, pro_record.uuid),
    ]

    main_course = (
        await db.exec(
            select(MapCourse).where(MapCourse.map_id == 981024, MapCourse.stage == 0)
        )
    ).one()
    await db.exec(
        delete(RecordPb).where(
            RecordPb.course_id == main_course.id,
            RecordPb.scope == 0,
        )
    )
    await db.commit()

    assert (
        await crud.read_map_wrs(
            session=db,
            map_id=981024,
            scope=RecordScope.OVR,
        )
    ) == []


async def test_record_pb_wr_unique_index_exists_and_map_wr_cache_removed(
    db: AsyncSession,
) -> None:
    record_pb_index = (
        await db.exec(
            text(
                """
                SELECT indexdef
                FROM pg_indexes
                WHERE schemaname = 'public'
                  AND tablename = 'record_pb'
                  AND indexname = 'ux_record_pb_wr_scope_course_type'
                """
            )
        )
    ).one()

    assert "UNIQUE INDEX ux_record_pb_wr_scope_course_type" in record_pb_index[0]
    assert "WHERE (points = 1000)" in record_pb_index[0]
    record_pb_updated_at_index = (
        await db.exec(
            text(
                """
                SELECT indexdef
                FROM pg_indexes
                WHERE schemaname = 'public'
                  AND tablename = 'record_pb'
                  AND indexname = 'ix_record_pb_updated_at_desc'
                """
            )
        )
    ).one()
    assert "INDEX ix_record_pb_updated_at_desc" in record_pb_updated_at_index[0]
    assert "updated_at DESC" in record_pb_updated_at_index[0]
    assert (
        await db.exec(text("SELECT to_regclass('cache.map_wrs')"))
    ).one() == (None,)
