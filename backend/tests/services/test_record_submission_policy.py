"""Native submission and heartbeat eligibility must use the same policy."""

import pytest
from fastapi import HTTPException
from sqlmodel import select

from app.models import KZMode, MapCourse, MapCourseTier, RecordFilter, ServerStatusPut
from app.models.record_upload import RecordCheck
from app.models.server import ServerRecordsStatusPut
from app.services.record_ingestion import accept_record, check_record
from app.services.record_replay_policy import effective_record_filter_mode
from app.services.record_submission_policy import mode_version_supported
from app.services.server_records_status import build_records_status
from tests.services.test_record_ingestion import setup_finish

pytestmark = pytest.mark.asyncio


async def readiness(db, group, server, run):
    return await build_records_status(
        db,
        group,
        server,
        ServerStatusPut(
            ip=server.ip,
            port=server.port,
            observed_at=run.finished_at,
            hostname="Submission policy test",
            map=run.map_name,
            player_count=0,
            max_players=32,
            gokz_top_status=ServerRecordsStatusPut(
                plugins_valid=True,
                settings_enforcer_valid=True,
                bsp_size=run.bsp_size,
                mode_versions={run.mode.value: run.mode_version},
            ),
        ),
    )


@pytest.mark.parametrize("mode", list(KZMode))
@pytest.mark.parametrize("delta", [-1, 0, 1])
async def test_mode_version_minimum_in_checks_submissions_and_readiness(
    db, mode, delta
):
    group, server, run = await setup_finish(db, mode)
    minimum = run.mode_version
    run.mode_version += delta
    result, _ = await check_record(db, group, run)
    assert result["checks"]["mode"] is (delta >= 0)
    assert result["required_mode_version"] == minimum
    status = await readiness(db, group, server, run)
    assert status["modes"][mode.value] is (delta >= 0)
    if delta < 0:
        with pytest.raises(HTTPException) as error:
            await accept_record(db, group, run, "older-mode")
        assert error.value.status_code == 422
    else:
        assert (await accept_record(db, group, run, "supported-mode"))["record_uuid"]


@pytest.mark.parametrize("mode", list(KZMode))
@pytest.mark.parametrize(
    "configuration",
    [
        "missing",
        "tier-only",
        "wildcard",
        "wrong-mode",
        "wrong-stage",
        "wrong-tickrate",
        "filter-only",
    ],
)
async def test_only_exact_record_filters_grant_availability(db, mode, configuration):
    group, server, run = await setup_finish(db, mode)
    record_filter = await db.get(RecordFilter, 982345)
    if configuration in {"missing", "tier-only"}:
        await db.delete(record_filter)
    elif configuration == "wildcard":
        record_filter.map_id = -1
    elif configuration == "wrong-mode":
        record_filter.mode = (
            KZMode.SKZ
            if effective_record_filter_mode(mode) == KZMode.KZT
            else KZMode.KZT
        )
    elif configuration == "wrong-stage":
        record_filter.stage = 1
    elif configuration == "wrong-tickrate":
        record_filter.tickrate = 64
    if configuration in {"missing", "filter-only"}:
        tier = (await db.exec(select(MapCourseTier))).one()
        await db.delete(tier)
    await db.flush()
    expected = configuration == "filter-only"
    result, _ = await check_record(db, group, run)
    assert result["checks"]["filter"] is expected
    assert result["eligible"] is expected
    status = await readiness(db, group, server, run)
    assert status["modes"][mode.value] is expected
    if not expected:
        with pytest.raises(HTTPException) as error:
            await accept_record(db, group, run, "unsupported-filter")
        assert error.value.status_code == 422
        assert error.value.detail["checks"]["filter"] is False
    else:
        assert (await accept_record(db, group, run, "exact-filter"))["record_uuid"]


@pytest.mark.parametrize("mode", list(KZMode))
@pytest.mark.parametrize("has_teleports", [False, True])
@pytest.mark.parametrize("teleports", [0, 1])
async def test_finish_category_and_category_agnostic_preflight(
    db, client, mode, has_teleports, teleports
):
    group, server, run = await setup_finish(db, mode)
    record_filter = await db.get(RecordFilter, 982345)
    record_filter.has_teleports = has_teleports
    run.teleports = teleports
    await db.flush()
    check = RecordCheck.model_validate(
        run.model_dump(exclude={"record_uuid", "time", "teleports", "finished_at"})
    )
    headers = {"X-Server-Group-Key": group.api_key, "Idempotency-Key": "category"}
    response = await client.post(
        "/v1/records/check", json=check.model_dump(mode="json"), headers=headers
    )
    assert response.status_code == 200
    assert response.json()["eligible"] is True
    assert (await readiness(db, group, server, run))["modes"][mode.value] is True
    response = await client.post(
        "/v1/records", json=run.model_dump(mode="json"), headers=headers
    )
    if teleports > 0 and not has_teleports:
        assert response.status_code == 422
        assert response.json()["detail"]["checks"]["filter"] is False
    else:
        assert response.status_code == 200
        assert response.json()["record_uuid"] == str(run.record_uuid)


@pytest.mark.parametrize("mode", list(KZMode))
async def test_bonus_requires_its_own_filter(db, mode):
    group, _, run = await setup_finish(db, mode)
    db.add(MapCourse(map_id=982345, stage=1))
    run.stage = 1
    await db.flush()
    assert not (await check_record(db, group, run))[0]["eligible"]
    record_filter = await db.get(RecordFilter, 982345)
    record_filter.stage = 1
    await db.flush()
    assert (await check_record(db, group, run))[0]["eligible"]
    assert (await accept_record(db, group, run, "bonus"))["record_uuid"]


@pytest.mark.parametrize("submitted,minimum", [(0, 0), (1, None), (0, 171)])
async def test_missing_version_evidence_is_ineligible(submitted, minimum):
    assert not mode_version_supported(submitted=submitted, minimum=minimum)
