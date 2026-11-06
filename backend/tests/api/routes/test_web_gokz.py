import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.v1.web_gokz import launch_codes
from app.core.config import settings
from app.models import KZMode, Map, Record, RecordPb, RecordReplay, User
from app.models.web_gokz import WebIdentity, WebTime
from app.services.web_gokz import Member, Room, rooms
from tests.utils.user import user_authentication_headers
from tests.utils.utils import random_steamid64

PREFIX = "/v1/web-gokz"


async def login(client: AsyncClient) -> tuple[dict[str, str], dict[str, str], str]:
    steamid = random_steamid64()
    site = await user_authentication_headers(client=client, steamid64=steamid)
    response = await client.post(f"{PREFIX}/session", headers=site)
    assert response.status_code == 200, response.text
    data = response.json()
    return site, {"Authorization": f"Bearer {data['access_token']}"}, str(steamid)


def finish(**overrides: object) -> dict[str, object]:
    return {
        "submission_id": str(uuid.uuid7()),
        "map_name": "kz_web_test",
        "map_version": "map-v1",
        "engine_version": "engine-v1",
        "mode": "KZT",
        "course": 0,
        "time_ms": 10000,
        "teleports": 0,
        **overrides,
    }


def filters(**overrides: str) -> dict[str, str]:
    return {
        "map_name": "kz_web_test",
        "map_version": "map-v1",
        "engine_version": "engine-v1",
        "mode": "KZT",
        **overrides,
    }


@pytest.mark.asyncio
async def test_web_records_are_isolated_idempotent_and_versioned(
    client: AsyncClient, db: AsyncSession
) -> None:
    site, web, steamid = await login(client)
    native_before = [
        (await db.exec(select(func.count()).select_from(table))).one()
        for table in (Record, RecordPb)
    ]
    body = finish()
    response = await client.post(f"{PREFIX}/records", headers=web, json=body)
    assert response.status_code == 200, response.text
    record = response.json()
    assert record["player"]["steamid64"] == steamid
    assert record["verification"] == "client-submitted"
    assert record["source"] == "solo"
    assert (await client.post(f"{PREFIX}/records", headers=web, json=body)).json()[
        "id"
    ] == record["id"]
    assert (
        await client.post(
            f"{PREFIX}/records", headers=web, json={**body, "time_ms": 9000}
        )
    ).status_code == 409
    assert (
        await client.post(f"{PREFIX}/records", headers=site, json=finish())
    ).status_code == 401
    assert (await client.get("/v1/users/me", headers=web)).status_code in (401, 403)
    for values in (
        {"time_ms": 9000, "teleports": 1},
        {"time_ms": 1000, "engine_version": "engine-v2"},
        {"time_ms": 1000, "map_version": "map-v2"},
    ):
        assert (
            await client.post(f"{PREFIX}/records", headers=web, json=finish(**values))
        ).status_code == 200
    top = (await client.get(f"{PREFIX}/records", params=filters())).json()
    assert top["count"] == 1
    assert top["data"][0]["time_ms"] == 9000
    pro = (await client.get(f"{PREFIX}/records", params=filters(type="PRO"))).json()
    assert pro["data"][0]["id"] == record["id"]
    pb = (
        await client.get(f"{PREFIX}/records/pb", params=filters(), headers=web)
    ).json()
    assert pb["record"]["time_ms"] == 9000
    assert (
        await client.get(
            f"{PREFIX}/records/pb", params=filters(mode="VNL"), headers=web
        )
    ).json() == {"record": None}
    assert native_before == [
        (await db.exec(select(func.count()).select_from(table))).one()
        for table in (Record, RecordPb)
    ]
    assert (await db.exec(select(func.count()).select_from(WebTime))).one() == 4


@pytest.mark.asyncio
async def test_room_finish_requires_current_member_map_and_generation(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    db.add(Map(id=987654, name="kz_web_test", difficulty=4))
    await db.commit()
    _, web, steamid = await login(client)
    room = Room(1, {"kz_web_test": "map-v1"}, "kz_web_test")
    rooms[1] = room
    try:
        body = finish(room_id=1, room_generation=str(room.generation))
        assert (
            await client.post(f"{PREFIX}/records", headers=web, json=body)
        ).status_code == 409
        member = Member(WebIdentity(steamid64=steamid, name="Player"))
        observer = Member(WebIdentity(steamid64="2", name="Observer"))
        room.join(member)
        room.join(observer)
        room.receive(
            member, {"type": "timer_start", "generation": str(room.generation)}, 31
        )
        room.receive(
            member,
            {
                "type": "state",
                "generation": str(room.generation),
                "position": [0, 0, 0],
                "angles": [0, 0],
                "crouched": False,
                "mode": "KZT",
                "timer_running": True,
                "timer_paused": True,
                "time_ms": 5000,
                "progress": 50,
            },
            32,
        )
        while not observer.queue.empty():
            observer.queue.get_nowait()
        result = (await client.post(f"{PREFIX}/records", headers=web, json=body)).json()
        assert result["source"] == "room"
        event = observer.queue.get_nowait()
        assert event == {
            "type": "finish",
            "player": result["player"],
            "map_name": body["map_name"],
            "mode": body["mode"],
            "time_ms": body["time_ms"],
            "teleports": 0,
            "record_id": result["id"],
            "generation": body["room_generation"],
        }
        assert member.finished and not member.running
        assert member.state and member.state["time_ms"] == body["time_ms"]
        assert member.state["progress"] == 100 and not member.state["timer_paused"]
        await client.post(f"{PREFIX}/records", headers=web, json=body)
        assert observer.queue.empty()
        server = (await client.get(f"{PREFIX}/servers")).json()["data"][0]
        assert server["group"]["name"] == "Web GOKZ"
        assert server["map_tier"] == 4
        assert server["source"] == {"type": "web_gokz", "room_id": 1}
        assert server["live_status"]["players"][0]["status"] == "finished"
        room.generation = uuid.uuid7()
        assert (
            await client.post(
                f"{PREFIX}/records",
                headers=web,
                json=finish(room_id=1, room_generation=body["room_generation"]),
            )
        ).status_code == 409
        assert (await client.get(f"{PREFIX}/rooms")).json()["data"][0]["players"][0][
            "steamid64"
        ] == steamid
        assert (await client.get(f"{PREFIX}/maps")).json()["data"] == [
            {"name": "kz_web_test", "bsp_sha256": "map-v1"}
        ]
    finally:
        rooms.clear()


@pytest.mark.asyncio
async def test_rejects_invalid_finishes_and_disabled_accounts(
    client: AsyncClient, db: AsyncSession
) -> None:
    _, web, steamid = await login(client)
    for bad in (
        {"time_ms": 0},
        {"time_ms": 1.5},
        {"time_ms": True},
        {"teleports": -1},
        {"mode": "OVR"},
        {"map_name": "../secret"},
        {"player_steamid64": 123},
        {"map_version": ""},
        {"room_generation": str(uuid.uuid7())},
    ):
        assert (
            await client.post(f"{PREFIX}/records", headers=web, json=finish(**bad))
        ).status_code == 422
    assert (await client.get(f"{PREFIX}/me", headers=web)).status_code == 200
    user = await db.get(User, int(steamid))
    assert user
    user.is_active = False
    await db.commit()
    assert (
        await client.post(f"{PREFIX}/records", headers=web, json=finish())
    ).status_code == 401


@pytest.mark.asyncio
async def test_leaderboard_best_per_player_pagination(client: AsyncClient) -> None:
    for milliseconds in (9000, 12000):
        _, web, _ = await login(client)
        for time_ms in (milliseconds, milliseconds + 1000):
            assert (
                await client.post(
                    f"{PREFIX}/records", headers=web, json=finish(time_ms=time_ms)
                )
            ).status_code == 200
    response = (
        await client.get(f"{PREFIX}/records", params=filters(limit="1", offset="1"))
    ).json()
    assert response["count"] == 2
    assert [row["time_ms"] for row in response["data"]] == [12000]


@pytest.mark.asyncio
async def test_launch_codes_are_short_lived_single_use_and_origin_bound(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "REPLAY_VIEWER_HOST", "https://game.example")
    site, web, steamid = await login(client)
    origin = {"Origin": "https://game.example"}
    try:
        assert (await client.post(f"{PREFIX}/launch", headers=web)).status_code == 403
        result = await client.post(f"{PREFIX}/launch", headers=site)
        assert result.status_code == 200
        code = result.json()["code"]
        assert result.json()["expires_in"] == 60
        assert (
            await client.post(
                f"{PREFIX}/session/exchange",
                json={"code": code},
                headers={"Origin": "https://attacker.example"},
            )
        ).status_code == 403
        response = await client.post(
            f"{PREFIX}/session/exchange", json={"code": code}, headers=origin
        )
        assert response.status_code == 200
        assert response.json()["player"]["steamid64"] == steamid
        assert (
            await client.post(
                f"{PREFIX}/session/exchange", json={"code": code}, headers=origin
            )
        ).status_code == 401
        code = (await client.post(f"{PREFIX}/launch", headers=site)).json()["code"]
        launch_codes[code] = (int(steamid), 0)
        assert (
            await client.post(
                f"{PREFIX}/session/exchange", json={"code": code}, headers=origin
            )
        ).status_code == 401
        code = (await client.post(f"{PREFIX}/launch", headers=site)).json()["code"]
        user = await db.get(User, int(steamid))
        assert user is not None
        user.is_active = False
        await db.commit()
        assert (
            await client.post(
                f"{PREFIX}/session/exchange", json={"code": code}, headers=origin
            )
        ).status_code == 401
        assert (
            await client.post(
                f"{PREFIX}/session/exchange", json={"code": "bad"}, headers=origin
            )
        ).status_code == 422
    finally:
        launch_codes.clear()


@pytest.mark.asyncio
async def test_progress_reference_prefers_requested_mode_and_skips_invalid_runs(
    client: AsyncClient, db: AsyncSession
) -> None:
    _, _, steamid = await login(client)
    map_ = Map(name="kz_web_reference")
    db.add(map_)
    await db.flush()
    assert map_.id is not None
    records = []
    for mode, runtime, valid, teleports, stage in (
        (KZMode.NKZ, "20", True, 0, 0),
        (KZMode.KZT, "10", True, 0, 0),
        (KZMode.NKZ, "1", False, 0, 0),
        (KZMode.NKZ, "2", True, 1, 0),
        (KZMode.NKZ, "3", True, 0, 1),
    ):
        record = Record(
            steamid64=int(steamid),
            map_id=map_.id,
            mode=mode,
            time=Decimal(runtime),
            is_valid=valid,
            teleports=teleports,
            stage=stage,
        )
        db.add(record)
        await db.flush()
        db.add(
            RecordReplay(
                record_uuid=record.uuid,
                storage="disk",
                key="/unused/reference.replay",
                size=1,
                checksum="0" * 64,
            )
        )
        records.append(record)
    await db.commit()
    for mode, expected in (
        ("NKZ", records[0]),
        ("KZT", records[1]),
        ("VNL", records[1]),
    ):
        result = (
            await client.get(
                f"{PREFIX}/maps/kz_web_reference/reference", params={"mode": mode}
            )
        ).json()
        assert result["url"].endswith(f"/v1/replays/{expected.uuid}")
    assert (await client.get(f"{PREFIX}/maps/kz_missing/reference")).json() == {
        "url": None
    }
