from datetime import UTC, datetime
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.core.config import settings
from app.models import (
    Map,
    MapLeaderboardCache,
    MapReviewSummaryCache,
    ModeScope,
    Player,
    RecordFilter,
    ServerGlobalapi,
)
from tests.utils.utils import random_steamid64

pytestmark = pytest.mark.asyncio


async def _create_player(db: AsyncSession, *, steamid64: int, name: str) -> None:
    db.add(Player(steamid64=steamid64, name=name))
    await db.flush()


async def _create_map(
    db: AsyncSession,
    *,
    map_id: int,
    name: str,
    difficulty: int,
    validated: bool = True,
) -> None:
    db.add(
        Map(
            id=map_id,
            name=name,
            filesize=1,
            validated=validated,
            difficulty=difficulty,
            approved_by_steamid64=0,
        )
    )
    await db.flush()


async def _create_record_filter(
    db: AsyncSession,
    *,
    record_filter_id: int,
    map_id: int,
    mode_id: int,
    tier: int,
) -> None:
    db.add(
        RecordFilter(
            id=record_filter_id,
            map_id=map_id,
            stage=0,
            mode_id=mode_id,
            tickrate=128,
            has_teleports=False,
            tier=tier,
            updated_by_id="0",
        )
    )
    await db.flush()


async def _create_server(db: AsyncSession, *, server_id: int) -> None:
    db.add(
        ServerGlobalapi(
            id=server_id,
            port=27015,
            ip="203.0.113.91",
            name="API Map Leaderboard Server",
            owner_steamid64=0,
            approval_status=1,
            approved_by_steamid64=0,
        )
    )
    await db.flush()


async def _create_record(
    db: AsyncSession,
    *,
    record_id: int,
    steamid64: int,
    server_id: int,
    map_id: int,
    mode_id: int,
    teleports: int,
    time_seconds: str,
) -> None:
    await crud.upsert_record(
        session=db,
        record_id=record_id,
        record_uuid=None,
        steamid64=steamid64,
        server_id=server_id,
        mode_id=mode_id,
        map_id=map_id,
        stage=0,
        time_seconds=Decimal(time_seconds),
        teleports=teleports,
        points=0,
        created_on=datetime(2099, 1, 1, tzinfo=UTC),
        updated_on=datetime(2099, 1, 1, tzinfo=UTC),
        updated_by=steamid64,
        replay_id=None,
        is_valid=True,
    )
    await db.flush()


async def test_read_map_leaderboard_returns_metrics_and_zero_rows(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    server_id = 2_140_000_010
    map_alpha_id = 2_140_000_001
    map_beta_id = 2_140_000_002
    map_hidden_id = 2_140_000_003
    player_id = random_steamid64()

    await _create_player(db, steamid64=player_id, name="API Reader")
    await _create_server(db, server_id=server_id)
    await _create_map(db, map_id=map_alpha_id, name="kz_api_alpha", difficulty=6)
    await _create_map(db, map_id=map_beta_id, name="kz_api_beta", difficulty=3)
    await _create_map(
        db,
        map_id=map_hidden_id,
        name="kz_api_hidden",
        difficulty=2,
        validated=False,
    )
    await _create_record_filter(
        db,
        record_filter_id=2_140_100_001,
        map_id=map_alpha_id,
        mode_id=200,
        tier=5,
    )
    await _create_record(
        db,
        record_id=2_140_200_001,
        steamid64=player_id,
        server_id=server_id,
        map_id=map_alpha_id,
        mode_id=200,
        teleports=1,
        time_seconds="12.000",
    )
    db.add(
        MapReviewSummaryCache(
            map_id=map_alpha_id,
            overall_avg=4.5,
            gameplay_avg=4.0,
            visuals_avg=4.8,
            reviews_count=2,
            gameplay_count=2,
            visuals_count=2,
            comments_count=1,
            updated_at=datetime(2099, 1, 2, tzinfo=UTC),
        )
    )
    await db.commit()

    response = await client.get(
        f"{settings.API_V1_STR}/leaderboards/maps",
        params={"scope": "KZT"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 2
    assert [entry["map"]["name"] for entry in payload["data"]] == [
        "kz_api_alpha",
        "kz_api_beta",
    ]

    alpha_entry = payload["data"][0]
    assert alpha_entry["tier"] == 5
    assert alpha_entry["review_summary"]["comments_count"] == 1
    assert alpha_entry["unique_player_finishes"] == 1
    assert alpha_entry["total_finishes"] == 1
    assert alpha_entry["total_playtime"] == 12.0

    beta_entry = payload["data"][1]
    assert beta_entry["tier"] == 3
    assert beta_entry["review_summary"] is None
    assert beta_entry["unique_player_finishes"] == 0
    assert beta_entry["total_finishes"] == 0
    assert beta_entry["updated_at"] is None


async def test_put_map_leaderboards_supports_targeted_rebuild(
    client: AsyncClient,
    db: AsyncSession,
    superuser_token_headers: dict[str, str],
) -> None:
    server_id = 2_141_000_010
    map_alpha_id = 2_141_000_001
    map_beta_id = 2_141_000_002
    player_id = random_steamid64()

    await _create_player(db, steamid64=player_id, name="Rebuilder")
    await _create_server(db, server_id=server_id)
    await _create_map(db, map_id=map_alpha_id, name="kz_api_target", difficulty=4)
    await _create_map(db, map_id=map_beta_id, name="kz_api_other", difficulty=7)
    await _create_record(
        db,
        record_id=2_141_100_001,
        steamid64=player_id,
        server_id=server_id,
        map_id=map_alpha_id,
        mode_id=200,
        teleports=1,
        time_seconds="10.000",
    )
    await _create_record(
        db,
        record_id=2_141_100_002,
        steamid64=player_id,
        server_id=server_id,
        map_id=map_beta_id,
        mode_id=202,
        teleports=1,
        time_seconds="20.000",
    )
    await db.exec(MapLeaderboardCache.__table__.delete())
    await db.commit()

    response = await client.put(
        f"{settings.API_V1_STR}/leaderboards/maps",
        params={"scope": "KZT", "map_id": map_alpha_id},
        headers=superuser_token_headers,
    )

    assert response.status_code == 200
    assert response.json() == {"message": "Map leaderboard rows rebuilt successfully"}
    alpha_row = await db.get(MapLeaderboardCache, (map_alpha_id, ModeScope.KZT))
    beta_row = await db.get(MapLeaderboardCache, (map_beta_id, ModeScope.VNL))
    assert alpha_row is not None
    assert alpha_row.total_finishes == 1
    assert beta_row is None
