from datetime import UTC, datetime
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlmodel import delete
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.core.config import settings
from app.models import (
    Ban,
    BanType,
    LeaderboardPlayer,
    Map,
    MapCourse,
    Player,
    RecordFilter,
    ServerGlobalapi,
)
from app.models.leaderboard_player import scale_public_rating
from app.models.record import RecordScopeId
from tests.utils.utils import random_steamid64

pytestmark = pytest.mark.asyncio


def _public_rating(value: int) -> float | None:
    return scale_public_rating(value)


async def _get_kzt_leaderboard_row(
    db: AsyncSession,
    *,
    steamid64: int,
) -> LeaderboardPlayer:
    row = await db.get(LeaderboardPlayer, (int(RecordScopeId.KZT), steamid64))
    assert row is not None
    return row


async def _create_player(
    db: AsyncSession,
    *,
    steamid64: int,
    name: str,
    custom_id: str | None = None,
    country: str | None = None,
) -> None:
    db.add(
        Player(
            steamid64=steamid64,
            name=name,
            custom_id=custom_id,
            country=country,
        )
    )
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


async def _create_ban(
    db: AsyncSession,
    *,
    ban_id: int,
    steamid64: int,
    expires_on: datetime | None,
) -> None:
    db.add(
        Ban(
            id=ban_id,
            ban_type=BanType.BHOP_HACK,
            expires_on=expires_on,
            steamid64=steamid64,
            player_name=f"Player {steamid64}",
            notes="cheater",
            stats="stats",
            server_id=1,
            updated_by_id="1",
            created_on=datetime(2099, 1, 2, tzinfo=UTC),
            updated_on=datetime(2099, 1, 2, tzinfo=UTC),
        )
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
    await _create_player(
        db, steamid64=alpha, name="Alpha", custom_id="alpha", country="DE"
    )
    await _create_player(db, steamid64=beta, name="Beta", country="FR")
    await _create_player(db, steamid64=gamma, name="Gamma", country="JP")
    await _create_player(db, steamid64=delta, name="Delta", country="IS")

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
    alpha_row = await _get_kzt_leaderboard_row(db, steamid64=players["alpha"])
    beta_row = await _get_kzt_leaderboard_row(db, steamid64=players["beta"])

    response = await client.get(
        f"{settings.API_V1_STR}/leaderboards/players",
        params={"scope": "KZT"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"][0]["player"]["steamid64"] == str(players["alpha"])
    assert payload["data"][0]["player"]["display_name"] == "Alpha"
    assert payload["data"][0]["rank"] == 1
    assert payload["data"][0]["rating"] == pytest.approx(_public_rating(alpha_row.rating))
    assert payload["data"][1]["player"]["steamid64"] == str(players["beta"])
    assert payload["data"][1]["player"]["display_name"] == "Beta"
    assert payload["data"][1]["rank"] == 2
    assert payload["data"][1]["rating"] == pytest.approx(_public_rating(beta_row.rating))
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
    delta_entry = next(
        entry
        for entry in payload["data"]
        if entry["player"]["steamid64"] == str(players["delta"])
    )
    assert delta_entry["rating"] is None
    assert delta_entry["rating_easy"] is None
    assert delta_entry["rating_hard"] is None


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


async def test_read_player_leaderboard_filters_by_country(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    players = await _seed_leaderboard_data(db)

    response = await client.get(
        f"{settings.API_V1_STR}/leaderboards/players",
        params={"scope": "KZT", "country": "DE"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert [entry["player"]["steamid64"] for entry in payload["data"]] == [
        str(players["alpha"])
    ]


async def test_read_player_leaderboard_filters_by_region(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    players = await _seed_leaderboard_data(db)

    response = await client.get(
        f"{settings.API_V1_STR}/leaderboards/players",
        params={"scope": "KZT", "region": "EU"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 2
    assert [entry["player"]["steamid64"] for entry in payload["data"]] == [
        str(players["alpha"]),
        str(players["beta"]),
    ]


async def test_read_player_leaderboard_rejects_country_and_region_together(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    await _seed_leaderboard_data(db)

    response = await client.get(
        f"{settings.API_V1_STR}/leaderboards/players",
        params={"scope": "KZT", "country": "DE", "region": "EU"},
    )

    assert response.status_code == 422
    assert "mutually exclusive" in response.text


async def test_read_player_leaderboard_rejects_invalid_region(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    await _seed_leaderboard_data(db)

    response = await client.get(
        f"{settings.API_V1_STR}/leaderboards/players",
        params={"scope": "KZT", "region": "ZZ"},
    )

    assert response.status_code == 422
    assert "Invalid region" in response.text


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


async def test_read_player_leaderboard_rank_returns_rating_rank_as_rank(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    players = await _seed_leaderboard_data(db)
    alpha_row = await _get_kzt_leaderboard_row(db, steamid64=players["alpha"])

    response = await client.get(
        f"{settings.API_V1_STR}/leaderboards/players/alpha",
        params={"scope": "KZT"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["scope"] == "KZT"
    assert payload["player"]["steamid64"] == str(players["alpha"])
    assert payload["player"]["display_name"] == "Alpha"
    assert payload["rank"] == 1
    assert payload["rank_regional"] == 1
    assert payload["region"] == "EU"
    assert "rating_rank" not in payload
    assert payload["points"] > payload["rating"]
    assert payload["rating"] == pytest.approx(_public_rating(alpha_row.rating))
    assert payload["rating_easy"] == pytest.approx(_public_rating(alpha_row.rating_easy))
    assert payload["rating_hard"] == pytest.approx(_public_rating(alpha_row.rating_hard))


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
    assert payload["rank"] is None
    assert payload["rank_regional"] is None
    assert payload["region"] == "EU"
    assert "rating_rank" not in payload
    assert payload["rating"] is None
    assert payload["rating_easy"] is None
    assert payload["rating_hard"] is None
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
    assert payload["rank_regional"] is None
    assert payload["region"] == "EU"
    assert "rating_rank" not in payload
    assert payload["points"] == 0
    assert payload["rating"] is None
    assert payload["rating_easy"] is None
    assert payload["rating_hard"] is None
    assert payload["unique_map_finishes"] == 0


async def test_read_player_leaderboard_excludes_actively_banned_players(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    players = await _seed_leaderboard_data(db)
    await _create_ban(
        db,
        ban_id=2_120_900_001,
        steamid64=players["alpha"],
        expires_on=None,
    )
    await db.commit()

    response = await client.get(
        f"{settings.API_V1_STR}/leaderboards/players",
        params={"scope": "KZT"},
    )

    assert response.status_code == 200
    steamids = [entry["player"]["steamid64"] for entry in response.json()["data"]]
    assert str(players["alpha"]) not in steamids
    assert str(players["beta"]) in steamids

    rank_response = await client.get(
        f"{settings.API_V1_STR}/leaderboards/players/alpha",
        params={"scope": "KZT"},
    )
    assert rank_response.status_code == 200
    assert rank_response.json()["rank"] is None
    assert rank_response.json()["rank_regional"] is None


async def test_read_player_leaderboard_keeps_expired_bans_out_of_exclusion(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    players = await _seed_leaderboard_data(db)
    await _create_ban(
        db,
        ban_id=2_120_900_002,
        steamid64=players["alpha"],
        expires_on=datetime(2000, 1, 1, tzinfo=UTC),
    )
    await db.commit()

    response = await client.get(
        f"{settings.API_V1_STR}/leaderboards/players",
        params={"scope": "KZT"},
    )
    assert response.status_code == 200
    steamids = [entry["player"]["steamid64"] for entry in response.json()["data"]]
    assert str(players["alpha"]) in steamids


async def test_read_player_leaderboard_rank_filters_by_country(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    players = await _seed_leaderboard_data(db)

    response = await client.get(
        f"{settings.API_V1_STR}/leaderboards/players/alpha",
        params={"scope": "KZT", "country": "DE"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["rank"] == 1
    assert payload["rank_regional"] == 1
    assert payload["region"] == "EU"
    assert payload["player"]["steamid64"] == str(players["alpha"])


async def test_read_player_leaderboard_rank_filters_by_region(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    players = await _seed_leaderboard_data(db)

    response = await client.get(
        f"{settings.API_V1_STR}/leaderboards/players/{players['beta']}",
        params={"scope": "KZT", "region": "EU"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["rank"] == 2
    assert payload["rank_regional"] == 2
    assert payload["region"] == "EU"
    assert payload["player"]["steamid64"] == str(players["beta"])


async def test_read_player_leaderboard_rank_returns_none_when_filtered_out(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    await _seed_leaderboard_data(db)

    response = await client.get(
        f"{settings.API_V1_STR}/leaderboards/players/alpha",
        params={"scope": "KZT", "country": "FR"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["rank"] is None
    assert payload["rank_regional"] == 1
    assert payload["region"] == "EU"


async def test_read_player_leaderboard_rank_returns_null_region_when_player_country_missing(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    player_steamid64 = random_steamid64()
    await _create_player(
        db,
        steamid64=player_steamid64,
        name="No Region",
        custom_id="no-region",
        country=None,
    )
    await db.commit()

    response = await client.get(
        f"{settings.API_V1_STR}/leaderboards/players/no-region",
        params={"scope": "OVR"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["player"]["steamid64"] == str(player_steamid64)
    assert payload["region"] is None
    assert payload["rank"] is None
    assert payload["rank_regional"] is None


async def test_read_regions_returns_region_metadata(client: AsyncClient) -> None:
    response = await client.get(f"{settings.API_V1_STR}/regions/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 9
    assert any(
        region["code"] == "EU" and "DE" in region["country_codes"]
        for region in payload["data"]
    )


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
