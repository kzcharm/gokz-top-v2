import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models import Ban, BanType, Jumpstat, JumpstatType, KZMode, Player
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
