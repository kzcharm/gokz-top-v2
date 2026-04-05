from datetime import UTC, datetime
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlmodel import delete
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.core.config import settings
from app.models import (
    LeaderboardPlayer,
    Map,
    MapCourse,
    Player,
    RecordFilter,
    ServerGlobalapi,
)
from app.models.record import RecordScopeId
from tests.utils.utils import random_steamid64

pytestmark = pytest.mark.asyncio


async def _create_player(
    db: AsyncSession,
    *,
    steamid64: int,
    name: str,
    custom_id: str | None = None,
) -> None:
    db.add(Player(steamid64=steamid64, name=name, custom_id=custom_id))
    await db.flush()


async def _create_map(
    db: AsyncSession,
    *,
    map_id: int,
    name: str,
    difficulty: int,
) -> tuple[int, int, int]:
    db.add(
        Map(
            id=map_id,
            name=name,
            filesize=1,
            validated=True,
            difficulty=difficulty,
            approved_by_steamid64=0,
        )
    )
    await db.flush()
    course = MapCourse(map_id=map_id, stage=0)
    db.add(course)
    await db.flush()
    assert course.id is not None
    return (course.id, map_id, 0)


async def _create_server(db: AsyncSession, *, server_id: int) -> None:
    db.add(
        ServerGlobalapi(
            id=server_id,
            port=27015,
            ip="203.0.113.80",
            name="Leaderboard API Server",
            owner_steamid64=0,
            approval_status=1,
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


async def _create_record(
    db: AsyncSession,
    *,
    record_id: int,
    steamid64: int,
    server_id: int,
    mode_id: int,
    map_id: int,
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


async def _seed_leaderboard_data(
    db: AsyncSession,
    *,
    rebuild: bool = True,
) -> dict[str, int]:
    await db.exec(delete(LeaderboardPlayer))
    await db.flush()

    server_id = 2_120_000_001
    await _create_server(db, server_id=server_id)

    alpha = random_steamid64()
    beta = random_steamid64()
    gamma = random_steamid64()
    delta = random_steamid64()
    await _create_player(db, steamid64=alpha, name="Alpha", custom_id="alpha")
    await _create_player(db, steamid64=beta, name="Beta")
    await _create_player(db, steamid64=gamma, name="Gamma")
    await _create_player(db, steamid64=delta, name="Delta")

    for index in range(20):
        map_id = 2_120_100_000 + index
        tier = 4 if index < 10 else 5
        await _create_map(
            db,
            map_id=map_id,
            name=f"kz_api_kzt_{index}",
            difficulty=tier,
        )
        await _create_record_filter(
            db,
            record_filter_id=2_120_200_000 + index,
            map_id=map_id,
            mode_id=200,
            tier=tier,
        )
        await _create_record(
            db,
            record_id=2_120_300_000 + index,
            steamid64=alpha,
            server_id=server_id,
            mode_id=200,
            map_id=map_id,
            teleports=1,
            time_seconds=f"{10 + index}.000",
        )
        await _create_record(
            db,
            record_id=2_120_400_000 + index,
            steamid64=beta,
            server_id=server_id,
            mode_id=200,
            map_id=map_id,
            teleports=1,
            time_seconds=f"{20 + index}.000",
        )
        if index < 19:
            await _create_record(
                db,
                record_id=2_120_500_000 + index,
                steamid64=delta,
                server_id=server_id,
                mode_id=200,
                map_id=map_id,
                teleports=1,
                time_seconds=f"{30 + index}.000",
            )

    await _create_record(
        db,
        record_id=2_120_600_000,
        steamid64=alpha,
        server_id=server_id,
        mode_id=200,
        map_id=2_120_100_000,
        teleports=0,
        time_seconds="9.000",
    )

    for index in range(20):
        map_id = 2_121_100_000 + index
        await _create_map(
            db,
            map_id=map_id,
            name=f"kz_api_skz_{index}",
            difficulty=5,
        )
        await _create_record_filter(
            db,
            record_filter_id=2_121_200_000 + index,
            map_id=map_id,
            mode_id=201,
            tier=5,
        )
        await _create_record(
            db,
            record_id=2_121_300_000 + index,
            steamid64=gamma,
            server_id=server_id,
            mode_id=201,
            map_id=map_id,
            teleports=1,
            time_seconds=f"{15 + index}.000",
        )

    if rebuild:
        await crud.rebuild_leaderboard_players(
            session=db,
            scope_ids=[
                int(RecordScopeId.OVR),
                int(RecordScopeId.KZT),
                int(RecordScopeId.SKZ),
            ],
            steamid64s=[alpha, beta, gamma, delta],
        )
        await db.commit()
    return {
        "alpha": alpha,
        "beta": beta,
        "gamma": gamma,
        "delta": delta,
    }


@pytest.mark.parametrize(
    "sort_by",
    [
        "rating",
        "rating_easy",
        "rating_hard",
        "points",
        "wrs_nub",
        "wrs_pro",
        "records_900_plus",
        "records_800_plus",
        "unique_map_finishes",
    ],
)
async def test_read_player_leaderboard_filters_to_positive_metric_rows(
    client: AsyncClient,
    db: AsyncSession,
    sort_by: str,
) -> None:
    await _seed_leaderboard_data(db)

    response = await client.get(
        f"{settings.API_V1_STR}/leaderboards/players",
        params={"scope": "KZT", "sort_by": sort_by},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] >= 1
    assert all(entry[sort_by] > 0 for entry in payload["data"])


async def test_read_player_leaderboard_default_sort_and_rank(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    players = await _seed_leaderboard_data(db)

    response = await client.get(
        f"{settings.API_V1_STR}/leaderboards/players",
        params={"scope": "KZT"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"][0]["player"]["steamid64"] == str(players["alpha"])
    assert payload["data"][0]["rank"] == 1
    assert payload["data"][1]["player"]["steamid64"] == str(players["beta"])
    assert payload["data"][1]["rank"] == 2
    assert str(players["delta"]) not in {
        entry["player"]["steamid64"] for entry in payload["data"]
    }


async def test_read_player_leaderboard_points_sort_includes_below_threshold_player(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    players = await _seed_leaderboard_data(db)

    response = await client.get(
        f"{settings.API_V1_STR}/leaderboards/players",
        params={"scope": "KZT", "sort_by": "points"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert str(players["delta"]) in {
        entry["player"]["steamid64"] for entry in payload["data"]
    }


async def test_read_player_leaderboard_scope_and_pagination(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    players = await _seed_leaderboard_data(db)

    skz_response = await client.get(
        f"{settings.API_V1_STR}/leaderboards/players",
        params={"scope": "SKZ"},
    )
    paged_response = await client.get(
        f"{settings.API_V1_STR}/leaderboards/players",
        params={"scope": "KZT", "offset": 1, "limit": 1},
    )

    assert skz_response.status_code == 200
    assert paged_response.status_code == 200

    skz_payload = skz_response.json()
    paged_payload = paged_response.json()
    assert skz_payload["count"] == 1
    assert skz_payload["data"][0]["player"]["steamid64"] == str(players["gamma"])
    assert paged_payload["count"] >= 2
    assert len(paged_payload["data"]) == 1
    assert paged_payload["data"][0]["player"]["steamid64"] == str(players["beta"])


async def test_read_player_leaderboard_rejects_asc_sort_order(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    await _seed_leaderboard_data(db)

    response = await client.get(
        f"{settings.API_V1_STR}/leaderboards/players",
        params={"scope": "KZT", "sort_order": "asc"},
    )

    assert response.status_code == 422
    assert "sort_order" in response.text


async def test_read_player_leaderboard_rank_returns_points_and_rating_rank(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    players = await _seed_leaderboard_data(db)

    response = await client.get(
        f"{settings.API_V1_STR}/leaderboards/players/alpha",
        params={"scope": "KZT"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["scope"] == "KZT"
    assert payload["player"]["steamid64"] == str(players["alpha"])
    assert payload["rank"] == 1
    assert payload["rating_rank"] == 1
    assert payload["points"] > payload["rating"]


async def test_read_player_leaderboard_rank_returns_unranked_rating_when_ineligible(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    players = await _seed_leaderboard_data(db)

    response = await client.get(
        f"{settings.API_V1_STR}/leaderboards/players/{players['delta']}",
        params={"scope": "KZT"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["player"]["steamid64"] == str(players["delta"])
    assert payload["rank"] == 3
    assert payload["rating_rank"] is None
    assert payload["rating"] == 0
    assert payload["points"] > 0


async def test_read_player_leaderboard_rank_returns_zeroed_scope_row_when_missing(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    players = await _seed_leaderboard_data(db)

    response = await client.get(
        f"{settings.API_V1_STR}/leaderboards/players/{players['beta']}",
        params={"scope": "SKZ"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["player"]["steamid64"] == str(players["beta"])
    assert payload["rank"] is None
    assert payload["rating_rank"] is None
    assert payload["points"] == 0
    assert payload["rating"] == 0
    assert payload["unique_map_finishes"] == 0


async def test_upsert_player_leaderboards_rebuilds_player_without_auth(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    players = await _seed_leaderboard_data(db, rebuild=False)

    before_response = await client.get(
        f"{settings.API_V1_STR}/leaderboards/players",
        params={"scope": "KZT"},
    )
    assert before_response.status_code == 200
    assert before_response.json() == {"data": [], "count": 0}

    rebuild_response = await client.put(
        f"{settings.API_V1_STR}/leaderboards/players/{players['alpha']}"
    )

    assert rebuild_response.status_code == 200
    assert rebuild_response.json() == {
        "message": "Player leaderboard rows rebuilt successfully"
    }

    after_response = await client.get(
        f"{settings.API_V1_STR}/leaderboards/players",
        params={"scope": "KZT"},
    )

    assert after_response.status_code == 200
    payload = after_response.json()
    assert payload["count"] == 1
    assert payload["data"][0]["player"]["steamid64"] == str(players["alpha"])
