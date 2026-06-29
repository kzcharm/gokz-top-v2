import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models import (
    Ban,
    BanType,
    Jumpstat,
    JumpstatType,
    JumpstatVisualizationBounds,
    JumpstatVisualizationJumpDirection,
    JumpstatVisualizationMouseDirection,
    JumpstatVisualizationPublic,
    JumpstatVisualizationSample,
    JumpstatVisualizationStrafeType,
    KZMode,
    Player,
)
from app.services.jump_replay_parser import JUMPSTAT_VISUALIZATION_VERSION
from app.services.jump_replay_storage import get_jump_replay_path, save_jump_replay
from tests.utils.jump_replay import (
    build_synthetic_jump_replay,
    expected_parent_values,
    expected_strafe_stats,
)
from tests.utils.server import create_server_group as create_test_server_group
from tests.utils.utils import random_steamid64

pytestmark = pytest.mark.asyncio


def _build_strafe_stats(*, strafes: int) -> list[dict[str, float | int]]:
    return [
        {
            "index": index,
            "sync_percent": min(100, 80 + index),
            "gain": float(12 + index),
            "loss": 0.0,
            "airtime_percent": 10 + index,
            "width": float(20 + index),
            "overlap_count": 0,
            "dead_air_count": 0,
        }
        for index in range(1, strafes + 1)
    ]


def _build_visualization_payload(
    *,
    version: int = JUMPSTAT_VISUALIZATION_VERSION,
) -> dict[str, object]:
    payload = JumpstatVisualizationPublic(
        version=JUMPSTAT_VISUALIZATION_VERSION,
        jump_direction=JumpstatVisualizationJumpDirection.FORWARDS,
        deviation_angle=12.5,
        bounds=JumpstatVisualizationBounds(
            min_x=-1.0,
            max_x=1.0,
            min_y=0.0,
            max_y=2.0,
        ),
        samples=[
            JumpstatVisualizationSample(
                index=0,
                x=0.0,
                y=0.0,
                yaw_delta=0.0,
                mouse_direction=JumpstatVisualizationMouseDirection.NONE,
                a_pressed=False,
                d_pressed=False,
                strafe_type=JumpstatVisualizationStrafeType.NONE,
            ),
            JumpstatVisualizationSample(
                index=1,
                x=0.5,
                y=1.5,
                yaw_delta=10.0,
                mouse_direction=JumpstatVisualizationMouseDirection.RIGHT,
                a_pressed=False,
                d_pressed=True,
                strafe_type=JumpstatVisualizationStrafeType.RIGHT,
            ),
        ],
    ).model_dump(mode="json")
    payload["version"] = version
    return payload


async def _create_player(
    db: AsyncSession,
    *,
    steamid64: int,
    name: str,
    alias: str | None = None,
    custom_id: str | None = None,
) -> Player:
    player = Player(
        steamid64=steamid64,
        name=name,
        alias=alias,
        custom_id=custom_id,
    )
    db.add(player)
    await db.commit()
    await db.refresh(player)
    return player


async def _create_jumpstat(
    db: AsyncSession,
    *,
    player_steamid64: int,
    server_group_id: uuid.UUID,
    type: JumpstatType = JumpstatType.LJ,
    mode: KZMode = KZMode.KZT,
    distance: str = "281.8030",
    block: int | None = 280,
    strafes: int = 9,
    sync_percent: int = 83,
    pre_speed: str = "276.1000",
    max_speed: str = "366.7200",
    w_count: int = 0,
    overlap_count: int = 0,
    dead_air_count: int = 0,
    width: str = "33.8000",
    height: str = "55.8000",
    airtime_percent: int = 100,
    offset: str = "0.0000",
    crouched_ticks: int = 21,
    edge: str | None = None,
    deviation: str | None = None,
    jumped_at: datetime | None = None,
    visualization_data: dict[str, object] | None = None,
) -> Jumpstat:
    jumpstat = Jumpstat(
        player_steamid64=player_steamid64,
        server_group_id=server_group_id,
        type=type,
        mode=mode,
        distance=Decimal(distance),
        block=block,
        strafes=strafes,
        sync_percent=sync_percent,
        pre_speed=Decimal(pre_speed),
        max_speed=Decimal(max_speed),
        w_count=w_count,
        overlap_count=overlap_count,
        dead_air_count=dead_air_count,
        width=Decimal(width),
        height=Decimal(height),
        airtime_percent=airtime_percent,
        offset=Decimal(offset),
        crouched_ticks=crouched_ticks,
        edge=Decimal(edge) if edge is not None else None,
        deviation=Decimal(deviation) if deviation is not None else None,
        strafe_stats=_build_strafe_stats(strafes=strafes),
        visualization_data=visualization_data,
        jumped_at=jumped_at or datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
        created_at=jumped_at or datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
        updated_at=jumped_at or datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
    )
    db.add(jumpstat)
    await db.commit()
    await db.refresh(jumpstat)
    return jumpstat


@pytest.mark.asyncio
async def test_read_jumpstats_returns_filtered_top_list(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    group, _api_key = await create_test_server_group(db, name="Jump Group")
    other_group, _other_api_key = await create_test_server_group(db, name="Other Group")
    first_player = await _create_player(
        db,
        steamid64=random_steamid64(),
        name="First Runner",
        alias="Alias Runner",
    )
    second_player = await _create_player(
        db,
        steamid64=random_steamid64(),
        name="Second Runner",
    )

    await _create_jumpstat(
        db,
        player_steamid64=first_player.steamid64,
        server_group_id=group.id,
        distance="281.8030",
        block=280,
        jumped_at=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
    )
    await _create_jumpstat(
        db,
        player_steamid64=second_player.steamid64,
        server_group_id=group.id,
        distance="279.1111",
        block=280,
        jumped_at=datetime(2026, 5, 1, 11, 0, tzinfo=UTC),
    )
    await _create_jumpstat(
        db,
        player_steamid64=first_player.steamid64,
        server_group_id=other_group.id,
        type=JumpstatType.BH,
        distance="290.0000",
        block=260,
    )

    response = await client.get(
        f"{settings.API_V1_STR}/jumpstats",
        params={
            "type": "LJ",
            "mode": "KZT",
            "block": 280,
            "server_group_id": str(group.id),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 2
    assert [row["distance"] for row in payload["data"]] == [281.803, 279.1111]
    assert payload["data"][0]["player"] == {
        "steamid64": str(first_player.steamid64),
        "display_name": "Alias Runner",
    }
    assert payload["data"][0]["server_group"] == {
        "id": str(group.id),
        "name": "Jump Group",
        "custom_id": group.custom_id,
    }
    assert "strafe_stats" not in payload["data"][0]


@pytest.mark.asyncio
async def test_read_jumpstat_detail_returns_strafe_stats(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    group, _api_key = await create_test_server_group(db, name="Detail Group")
    player = await _create_player(
        db,
        steamid64=random_steamid64(),
        name="Detail Runner",
    )
    jumpstat = await _create_jumpstat(
        db,
        player_steamid64=player.steamid64,
        server_group_id=group.id,
    )

    response = await client.get(f"{settings.API_V1_STR}/jumpstats/{jumpstat.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == str(jumpstat.id)
    assert payload["type"] == "LJ"
    assert payload["pre_speed"] == 276.1
    assert payload["max_speed"] == 366.72
    assert len(payload["strafe_stats"]) == 9
    assert payload["strafe_stats"][0] == {
        "index": 1,
        "sync_percent": 81,
        "gain": 13.0,
        "loss": 0.0,
        "airtime_percent": 11,
        "width": 21.0,
        "overlap_count": 0,
        "dead_air_count": 0,
    }


@pytest.mark.asyncio
async def test_read_jumpstat_visualization_returns_cached_payload(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    group, _api_key = await create_test_server_group(db, name="Visualization Group")
    player = await _create_player(
        db,
        steamid64=random_steamid64(),
        name="Visualization Runner",
    )
    jumpstat = await _create_jumpstat(
        db,
        player_steamid64=player.steamid64,
        server_group_id=group.id,
        visualization_data=_build_visualization_payload(),
    )

    response = await client.get(
        f"{settings.API_V1_STR}/jumpstats/{jumpstat.id}/visualization"
    )

    assert response.status_code == 200
    assert response.json() == _build_visualization_payload()


@pytest.mark.asyncio
async def test_read_jumpstat_visualization_builds_and_persists_missing_cache(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    group, _api_key = await create_test_server_group(db, name="Visualization Build Group")
    player = await _create_player(
        db,
        steamid64=random_steamid64(),
        name="Build Runner",
    )
    jumpstat = await _create_jumpstat(
        db,
        player_steamid64=player.steamid64,
        server_group_id=group.id,
    )
    synthetic = build_synthetic_jump_replay()
    monkeypatch.setattr(settings, "REPLAY_STORAGE_DIR", tmp_path)
    save_jump_replay(jumpstat_id=jumpstat.id, replay_bytes=synthetic.replay_bytes)

    response = await client.get(
        f"{settings.API_V1_STR}/jumpstats/{jumpstat.id}/visualization"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["version"] == JUMPSTAT_VISUALIZATION_VERSION
    assert payload["jump_direction"] == "FORWARDS"
    assert payload["deviation_angle"] == pytest.approx(11.3099, abs=1e-4)
    assert len(payload["samples"]) == 4

    await db.refresh(jumpstat)
    assert jumpstat.visualization_data is not None
    assert jumpstat.visualization_data["version"] == JUMPSTAT_VISUALIZATION_VERSION


@pytest.mark.asyncio
async def test_read_jumpstat_visualization_rebuilds_outdated_cache(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    group, _api_key = await create_test_server_group(db, name="Visualization Rebuild Group")
    player = await _create_player(
        db,
        steamid64=random_steamid64(),
        name="Rebuild Runner",
    )
    jumpstat = await _create_jumpstat(
        db,
        player_steamid64=player.steamid64,
        server_group_id=group.id,
        visualization_data=_build_visualization_payload(
            version=JUMPSTAT_VISUALIZATION_VERSION - 1
        ),
    )
    synthetic = build_synthetic_jump_replay()
    monkeypatch.setattr(settings, "REPLAY_STORAGE_DIR", tmp_path)
    save_jump_replay(jumpstat_id=jumpstat.id, replay_bytes=synthetic.replay_bytes)

    response = await client.get(
        f"{settings.API_V1_STR}/jumpstats/{jumpstat.id}/visualization"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["version"] == JUMPSTAT_VISUALIZATION_VERSION
    assert payload["deviation_angle"] == pytest.approx(11.3099, abs=1e-4)
    assert payload["samples"] != _build_visualization_payload(
        version=JUMPSTAT_VISUALIZATION_VERSION - 1
    )["samples"]

    await db.refresh(jumpstat)
    assert jumpstat.visualization_data is not None
    assert jumpstat.visualization_data["version"] == JUMPSTAT_VISUALIZATION_VERSION


@pytest.mark.asyncio
async def test_read_jumpstat_visualization_returns_409_when_replay_is_missing(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    group, _api_key = await create_test_server_group(db, name="Visualization Missing Group")
    player = await _create_player(
        db,
        steamid64=random_steamid64(),
        name="Missing Replay Runner",
    )
    jumpstat = await _create_jumpstat(
        db,
        player_steamid64=player.steamid64,
        server_group_id=group.id,
    )

    response = await client.get(
        f"{settings.API_V1_STR}/jumpstats/{jumpstat.id}/visualization"
    )

    assert response.status_code == 409
    assert ".replay" in response.json()["detail"]


@pytest.mark.asyncio
async def test_read_jumpstat_visualization_returns_409_when_replay_is_invalid(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    group, _api_key = await create_test_server_group(db, name="Visualization Invalid Group")
    player = await _create_player(
        db,
        steamid64=random_steamid64(),
        name="Invalid Replay Runner",
    )
    jumpstat = await _create_jumpstat(
        db,
        player_steamid64=player.steamid64,
        server_group_id=group.id,
    )
    monkeypatch.setattr(settings, "REPLAY_STORAGE_DIR", tmp_path)
    save_jump_replay(jumpstat_id=jumpstat.id, replay_bytes=b"not-a-replay")

    response = await client.get(
        f"{settings.API_V1_STR}/jumpstats/{jumpstat.id}/visualization"
    )

    assert response.status_code == 409
    assert "invalid replay magic" in response.json()["detail"]


@pytest.mark.asyncio
async def test_read_player_jumpstats_resolves_identifier_and_filters(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    group, _api_key = await create_test_server_group(db, name="Player Group")
    player = await _create_player(
        db,
        steamid64=random_steamid64(),
        name="History Runner",
        custom_id="jump-runner",
    )
    await _create_jumpstat(
        db,
        player_steamid64=player.steamid64,
        server_group_id=group.id,
        type=JumpstatType.LJ,
    )
    await _create_jumpstat(
        db,
        player_steamid64=player.steamid64,
        server_group_id=group.id,
        type=JumpstatType.BH,
        distance="260.0000",
    )

    response = await client.get(
        f"{settings.API_V1_STR}/players/jump-runner/jumpstats",
        params={"type": "BH"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["data"][0]["type"] == "BH"
    assert payload["data"][0]["player"]["steamid64"] == str(player.steamid64)
    assert payload["data"][0]["server_group"] == {
        "id": str(group.id),
        "name": "Player Group",
        "custom_id": group.custom_id,
    }


@pytest.mark.asyncio
async def test_read_player_jumpstats_block_sort_uses_distance_tiebreaker(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    group, _api_key = await create_test_server_group(db, name="Block Sort Group")
    player = await _create_player(
        db,
        steamid64=random_steamid64(),
        name="Block Runner",
        custom_id="block-runner",
    )
    await _create_jumpstat(
        db,
        player_steamid64=player.steamid64,
        server_group_id=group.id,
        type=JumpstatType.LJ,
        distance="282.0000",
        block=280,
        jumped_at=datetime(2026, 5, 1, 11, 0, tzinfo=UTC),
    )
    await _create_jumpstat(
        db,
        player_steamid64=player.steamid64,
        server_group_id=group.id,
        type=JumpstatType.LJ,
        distance="281.5000",
        block=282,
        jumped_at=datetime(2026, 5, 1, 10, 0, tzinfo=UTC),
    )
    await _create_jumpstat(
        db,
        player_steamid64=player.steamid64,
        server_group_id=group.id,
        type=JumpstatType.LJ,
        distance="281.7500",
        block=282,
        jumped_at=datetime(2026, 5, 1, 9, 0, tzinfo=UTC),
    )

    response = await client.get(
        f"{settings.API_V1_STR}/players/block-runner/jumpstats",
        params={"type": "LJ", "sort_by": "block"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 3
    assert [entry["block"] for entry in payload["data"]] == [282, 282, 280]
    assert [entry["distance"] for entry in payload["data"]] == [
        281.75,
        281.5,
        282.0,
    ]


@pytest.mark.asyncio
async def test_jumpstat_lists_exclude_banned_players_by_default_but_detail_remains_available(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    group, _api_key = await create_test_server_group(db, name="Banned Group")
    player = await _create_player(
        db,
        steamid64=random_steamid64(),
        name="Banned Runner",
    )
    jumpstat = await _create_jumpstat(
        db,
        player_steamid64=player.steamid64,
        server_group_id=group.id,
    )
    db.add(
        Ban(
            id=910001,
            steamid64=player.steamid64,
            ban_type=BanType.OTHER,
            created_at=datetime(2026, 5, 2, 12, 0, tzinfo=UTC),
            updated_at=datetime(2026, 5, 2, 12, 0, tzinfo=UTC),
            synced_at=datetime(2026, 5, 2, 12, 0, tzinfo=UTC),
        )
    )
    await db.commit()

    list_response = await client.get(f"{settings.API_V1_STR}/jumpstats")
    assert list_response.status_code == 200
    assert list_response.json() == {"data": [], "count": 0}

    included_response = await client.get(
        f"{settings.API_V1_STR}/jumpstats",
        params={"exclude_cheaters": "false"},
    )
    assert included_response.status_code == 200
    assert included_response.json()["count"] == 1

    detail_response = await client.get(f"{settings.API_V1_STR}/jumpstats/{jumpstat.id}")
    assert detail_response.status_code == 200
    assert detail_response.json()["player"]["steamid64"] == str(player.steamid64)


@pytest.mark.asyncio
async def test_create_jumpstat_upload_creates_row_and_replay_file(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    group, api_key = await create_test_server_group(db, name="Upload Group")
    monkeypatch.setattr(settings, "REPLAY_STORAGE_DIR", tmp_path)
    synthetic = build_synthetic_jump_replay()

    response = await client.post(
        f"{settings.API_V1_STR}/jumpstats",
        files={
            "replay": (
                "synthetic.replay",
                synthetic.replay_bytes,
                "application/octet-stream",
            )
        },
        headers={"X-Server-Group-Key": api_key},
    )

    assert response.status_code == 201
    payload = response.json()
    expected = expected_parent_values()
    assert payload["player"]["steamid64"] == str(synthetic.steamid64)
    assert payload["server_group"]["id"] == str(group.id)
    assert payload["distance"] == float(expected["distance"])
    assert payload["deviation"] == float(expected["deviation"])
    assert payload["edge"] is None
    assert payload["strafe_stats"] == expected_strafe_stats()

    jumpstat_id = uuid.UUID(payload["id"])
    stored_path = get_jump_replay_path(jumpstat_id=jumpstat_id)
    assert stored_path.exists()
    assert stored_path.read_bytes() == synthetic.replay_bytes

    created_jumpstats = list((await db.exec(select(Jumpstat))).all())
    assert len(created_jumpstats) == 1
    stored_player = await db.get(Player, synthetic.steamid64)
    assert stored_player is not None
    assert stored_player.name == str(synthetic.steamid64)


@pytest.mark.asyncio
async def test_create_jumpstat_upload_deduplicates_matching_replay(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    _group, api_key = await create_test_server_group(db, name="Repeat Upload Group")
    monkeypatch.setattr(settings, "REPLAY_STORAGE_DIR", tmp_path)
    synthetic = build_synthetic_jump_replay()

    first = await client.post(
        f"{settings.API_V1_STR}/jumpstats",
        files={
            "replay": (
                "synthetic.replay",
                synthetic.replay_bytes,
                "application/octet-stream",
            )
        },
        headers={"X-Server-Group-Key": api_key},
    )
    second = await client.post(
        f"{settings.API_V1_STR}/jumpstats",
        files={
            "replay": (
                "synthetic.replay",
                synthetic.replay_bytes,
                "application/octet-stream",
            )
        },
        headers={"X-Server-Group-Key": api_key},
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    jumpstats = list(
        (await db.exec(select(Jumpstat).order_by(Jumpstat.created_at))).all()
    )
    assert len(jumpstats) == 1


@pytest.mark.asyncio
async def test_create_jumpstat_raw_replay_upload_creates_row_and_replay_file(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    group, api_key = await create_test_server_group(db, name="Raw Upload Group")
    monkeypatch.setattr(settings, "REPLAY_STORAGE_DIR", tmp_path)
    synthetic = build_synthetic_jump_replay()

    response = await client.post(
        f"{settings.API_V1_STR}/jumpstats/replay",
        content=synthetic.replay_bytes,
        headers={
            "Content-Type": "application/octet-stream",
            "X-Server-Group-Key": api_key,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["player"]["steamid64"] == str(synthetic.steamid64)
    assert payload["server_group"]["id"] == str(group.id)
    assert get_jump_replay_path(jumpstat_id=uuid.UUID(payload["id"])).read_bytes() == (
        synthetic.replay_bytes
    )


@pytest.mark.asyncio
async def test_read_jump_replay_eligibility_returns_keep_decision(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    group, _api_key = await create_test_server_group(db, name="Eligibility Group")
    player = await _create_player(
        db,
        steamid64=random_steamid64(),
        name="Eligibility Runner",
    )
    for index in range(10):
        await _create_jumpstat(
            db,
            player_steamid64=player.steamid64,
            server_group_id=group.id,
            distance=str(300 - index),
            jumped_at=datetime(2026, 5, 1, 12, index, tzinfo=UTC),
        )

    response = await client.get(
        f"{settings.API_V1_STR}/jumpstats/replay-eligibility",
        params={
            "player_steamid64": str(player.steamid64),
            "mode": "KZT",
            "type": "LJ",
            "distance": "281.0000",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "eligible": False,
        "keep_limit": 10,
        "rank": 11,
        "cutoff_distance": 291.0,
        "cutoff_jumped_at": "2026-05-01T12:09:00Z",
    }


@pytest.mark.asyncio
async def test_create_jumpstat_upload_rejects_replay_below_retention_cutoff(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    group, api_key = await create_test_server_group(db, name="Retention Upload Group")
    monkeypatch.setattr(settings, "REPLAY_STORAGE_DIR", tmp_path)
    synthetic = build_synthetic_jump_replay()
    await _create_player(
        db,
        steamid64=synthetic.steamid64,
        name="Retention Runner",
    )
    for index in range(10):
        await _create_jumpstat(
            db,
            player_steamid64=synthetic.steamid64,
            server_group_id=group.id,
            distance=str(400 - index),
            jumped_at=datetime(2026, 5, 1, 12, index, tzinfo=UTC),
        )

    response = await client.post(
        f"{settings.API_V1_STR}/jumpstats",
        files={
            "replay": (
                "synthetic.replay",
                synthetic.replay_bytes,
                "application/octet-stream",
            )
        },
        headers={"X-Server-Group-Key": api_key},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Jump replay is not eligible for retention"
    assert list(tmp_path.rglob("*.replay")) == []


@pytest.mark.asyncio
async def test_create_jumpstat_upload_rejects_invalid_style(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    _group, api_key = await create_test_server_group(db, name="Invalid Upload Group")
    synthetic = build_synthetic_jump_replay(style_index=1)

    response = await client.post(
        f"{settings.API_V1_STR}/jumpstats",
        files={
            "replay": (
                "invalid.replay",
                synthetic.replay_bytes,
                "application/octet-stream",
            )
        },
        headers={"X-Server-Group-Key": api_key},
    )

    assert response.status_code == 422
    assert "unsupported replay style" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_jumpstat_upload_requires_valid_server_group_key(
    client: AsyncClient,
) -> None:
    synthetic = build_synthetic_jump_replay()

    response = await client.post(
        f"{settings.API_V1_STR}/jumpstats",
        files={
            "replay": (
                "synthetic.replay",
                synthetic.replay_bytes,
                "application/octet-stream",
            )
        },
        headers={"X-Server-Group-Key": "not-a-key"},
    )

    assert response.status_code == 401
