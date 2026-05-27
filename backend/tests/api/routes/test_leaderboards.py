import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.core.config import settings
from app.models import (
    Ban,
    BanType,
    Jumpstat,
    JumpstatType,
    KZMode,
    LeaderboardPlayer,
    Map,
    MapCourse,
    MapCourseTier,
    ModeScope,
    ModeScopeId,
    Player,
    RecordFilter,
    ServerGlobalapi,
    legacy_mode_id_to_kz_mode,
)
from app.models.leaderboard_player import (
    min_raw_rating_for_public_rating,
    scale_public_rating,
)
from tests.utils.server import create_server_group as create_test_server_group
from tests.utils.user import authentication_token_from_steamid
from tests.utils.utils import random_steamid64

pytestmark = pytest.mark.asyncio


def _public_rating(value: int) -> float | None:
    return scale_public_rating(value)


async def _get_kzt_leaderboard_row(
    db: AsyncSession,
    *,
    steamid64: int,
) -> LeaderboardPlayer:
    row = await db.get(LeaderboardPlayer, (ModeScope.KZT, steamid64))
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
            owner_steamid64=None,
            approval_status=1,
            approved_by_steamid64=None,
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
    course = (
        await db.exec(
            select(MapCourse).where(
                MapCourse.map_id == map_id,
                MapCourse.stage == 0,
            )
        )
    ).first()
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
    if course is not None and course.id is not None:
        mode = legacy_mode_id_to_kz_mode(mode_id)
        existing = await db.get(MapCourseTier, (course.id, mode))
        if existing is None:
            db.add(
                MapCourseTier(
                    course_id=course.id,
                    mode=mode,
                    tier=tier,
                    updated_by_id="0",
                )
            )
        else:
            positive_tiers = [value for value in (existing.tier, tier) if value > 0]
            existing.tier = min(positive_tiers) if positive_tiers else 0
            db.add(existing)
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
            notes="cheater",
            stats="stats",
            server_id=1,
            updated_by_id="1",
            created_on=datetime(2099, 1, 2, tzinfo=UTC),
            updated_on=datetime(2099, 1, 2, tzinfo=UTC),
        )
    )
    await db.flush()


async def _create_jumpstat(
    db: AsyncSession,
    *,
    player_steamid64: int,
    server_group_id: uuid.UUID,
    type: JumpstatType = JumpstatType.LJ,
    mode: KZMode = KZMode.KZT,
    distance: str = "281.8030",
    block: int | None = 280,
    strafes: int = 8,
    sync_percent: int = 83,
    pre_speed: str = "276.1000",
    max_speed: str = "366.7200",
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
        w_count=0,
        overlap_count=0,
        dead_air_count=0,
        width=Decimal("33.8000"),
        height=Decimal("55.8000"),
        airtime_percent=100,
        offset=Decimal("0.0000"),
        crouched_ticks=21,
        edge=None,
        deviation=None,
        strafe_stats=[
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
        ],
        jumped_at=jumped_at or datetime(2099, 2, 1, 12, 0, tzinfo=UTC),
        created_at=jumped_at or datetime(2099, 2, 1, 12, 0, tzinfo=UTC),
        updated_at=jumped_at or datetime(2099, 2, 1, 12, 0, tzinfo=UTC),
    )
    db.add(jumpstat)
    await db.flush()
    return jumpstat


async def _create_friendship(
    db: AsyncSession,
    *,
    player_steamid64: int,
    friend_steamid64: int,
) -> None:
    await crud.upsert_player_friend_edges(
        session=db,
        edges=[
            (player_steamid64, friend_steamid64, None),
            (friend_steamid64, player_steamid64, None),
        ],
    )
    await db.flush()


async def _set_leaderboard_rating(
    db: AsyncSession,
    *,
    scope: ModeScope,
    steamid64: int,
    rating: int,
) -> None:
    row = await db.get(LeaderboardPlayer, (scope, steamid64))
    assert row is not None
    row.rating = rating
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
        if index < 9:
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
                int(ModeScopeId.OVR),
                int(ModeScopeId.KZT),
                int(ModeScopeId.SKZ),
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
async def test_read_player_leaderboard_uses_stable_scope_membership_across_sorts(
    client: AsyncClient,
    db: AsyncSession,
    sort_by: str,
) -> None:
    players = await _seed_leaderboard_data(db)
    expected_order = (
        [str(players["beta"]), str(players["alpha"])]
        if sort_by in {"records_900_plus", "records_800_plus"}
        else [str(players["alpha"]), str(players["beta"])]
    )

    response = await client.get(
        f"{settings.API_V1_STR}/leaderboards/players",
        params={"scope": "KZT", "sort_by": sort_by},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 2
    assert [entry["player"]["steamid64"] for entry in payload["data"]] == expected_order


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
    assert payload["data"][0]["raw_rating"] == alpha_row.rating
    assert payload["data"][1]["player"]["steamid64"] == str(players["beta"])
    assert payload["data"][1]["player"]["display_name"] == "Beta"
    assert payload["data"][1]["rank"] == 2
    assert payload["data"][1]["rating"] == pytest.approx(_public_rating(beta_row.rating))
    assert payload["data"][1]["raw_rating"] == beta_row.rating
    assert len(payload["data"]) == 2


async def test_read_player_leaderboard_points_sort_excludes_below_threshold_player(
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
    assert str(players["delta"]) not in {
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
    assert paged_payload["count"] == 2
    assert len(paged_payload["data"]) == 1
    assert paged_payload["data"][0]["player"]["steamid64"] == str(players["beta"])


async def test_read_player_leaderboard_can_skip_count(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    await _seed_leaderboard_data(db)

    response = await client.get(
        f"{settings.API_V1_STR}/leaderboards/players",
        params={"scope": "KZT", "include_count": "false"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == -1
    assert len(payload["data"]) == 2


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


async def test_read_player_leaderboard_friends_only_filters_to_authenticated_users_friends(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    players = await _seed_leaderboard_data(db)
    await _create_friendship(
        db,
        player_steamid64=players["alpha"],
        friend_steamid64=players["beta"],
    )
    headers = await authentication_token_from_steamid(
        client=client,
        steamid64=players["alpha"],
        db=db,
    )

    response = await client.get(
        f"{settings.API_V1_STR}/leaderboards/players",
        params={"scope": "KZT", "friends_only": "true"},
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 2
    assert [row["player"]["steamid64"] for row in payload["data"]] == [
        str(players["alpha"]),
        str(players["beta"]),
    ]
    assert payload["data"][0]["rank"] == 1
    assert payload["data"][0]["global_rank"] == 1
    assert payload["data"][1]["rank"] == 2
    assert payload["data"][1]["global_rank"] == 2


async def test_read_player_leaderboard_friends_only_requires_authentication(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    await _seed_leaderboard_data(db)

    response = await client.get(
        f"{settings.API_V1_STR}/leaderboards/players",
        params={"scope": "KZT", "friends_only": "true"},
    )

    assert response.status_code == 403
    assert "friends-only leaderboard" in response.text


async def test_read_player_leaderboard_friends_only_rejects_geography_filters(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    players = await _seed_leaderboard_data(db)
    headers = await authentication_token_from_steamid(
        client=client,
        steamid64=players["alpha"],
        db=db,
    )

    response = await client.get(
        f"{settings.API_V1_STR}/leaderboards/players",
        params={
            "scope": "KZT",
            "friends_only": "true",
            "country": "DE",
        },
        headers=headers,
    )

    assert response.status_code == 422
    assert "friends_only" in response.text


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


async def test_read_player_leaderboard_rank_returns_zeroed_scope_row_when_ineligible(
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
    assert payload["points"] == 0
    assert payload["rating"] == 0
    assert payload["rating_easy"] == 0
    assert payload["rating_hard"] == 0
    assert payload["unique_map_finishes"] == 0


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
    assert payload["rating"] == 0
    assert payload["rating_easy"] == 0
    assert payload["rating_hard"] == 0
    assert payload["unique_map_finishes"] == 0


async def test_read_player_leaderboard_rank_zeroes_active_banned_player(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    players = await _seed_leaderboard_data(db)
    await _create_ban(
        db,
        ban_id=2_120_900_010,
        steamid64=players["alpha"],
        expires_on=None,
    )
    await db.commit()

    response = await client.get(
        f"{settings.API_V1_STR}/leaderboards/players/alpha",
        params={"scope": "KZT"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["player"]["steamid64"] == str(players["alpha"])
    assert payload["rank"] is None
    assert payload["global_rank"] is None
    assert payload["rank_regional"] is None
    assert payload["points"] == 0
    assert payload["rating"] == 0
    assert payload["rating_easy"] == 0
    assert payload["rating_hard"] == 0
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
    assert len(steamids) == 1

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


async def test_read_player_leaderboard_rank_friends_only_returns_slice_and_global_rank(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    players = await _seed_leaderboard_data(db)
    await _create_friendship(
        db,
        player_steamid64=players["alpha"],
        friend_steamid64=players["beta"],
    )
    headers = await authentication_token_from_steamid(
        client=client,
        steamid64=players["alpha"],
        db=db,
    )

    response = await client.get(
        f"{settings.API_V1_STR}/leaderboards/players/{players['beta']}",
        params={"scope": "KZT", "friends_only": "true"},
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["rank"] == 2
    assert payload["global_rank"] == 2
    assert payload["rank_regional"] == 2
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
    response = await client.get(f"{settings.API_V1_STR}/regions")

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
        f"{settings.API_V1_STR}/leaderboards/players/alpha"
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


async def test_read_jumpstat_leaderboard_returns_pb_rows_for_scope_and_type(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    players = await _seed_leaderboard_data(db)
    await _set_leaderboard_rating(
        db, scope=ModeScope.KZT, steamid64=players["alpha"], rating=40_000
    )
    await _set_leaderboard_rating(
        db, scope=ModeScope.KZT, steamid64=players["beta"], rating=39_000
    )
    group, _api_key = await create_test_server_group(db, name="Jumpstats Leaderboard")

    await _create_jumpstat(
        db,
        player_steamid64=players["alpha"],
        server_group_id=group.id,
        type=JumpstatType.LJ,
        mode=KZMode.KZT,
        distance="281.1111",
        block=280,
        jumped_at=datetime(2099, 2, 1, 12, 0, tzinfo=UTC),
    )
    await _create_jumpstat(
        db,
        player_steamid64=players["alpha"],
        server_group_id=group.id,
        type=JumpstatType.LJ,
        mode=KZMode.KZT,
        distance="284.4444",
        block=282,
        jumped_at=datetime(2099, 2, 1, 13, 0, tzinfo=UTC),
    )
    await _create_jumpstat(
        db,
        player_steamid64=players["alpha"],
        server_group_id=group.id,
        type=JumpstatType.BH,
        mode=KZMode.KZT,
        distance="289.9999",
        block=286,
    )
    await _create_jumpstat(
        db,
        player_steamid64=players["beta"],
        server_group_id=group.id,
        type=JumpstatType.LJ,
        mode=KZMode.KZT,
        distance="279.5555",
        block=279,
        jumped_at=datetime(2099, 2, 1, 11, 0, tzinfo=UTC),
    )
    await _create_jumpstat(
        db,
        player_steamid64=players["gamma"],
        server_group_id=group.id,
        type=JumpstatType.LJ,
        mode=KZMode.SKZ,
        distance="300.1234",
        block=290,
    )
    await db.commit()

    response = await client.get(
        f"{settings.API_V1_STR}/leaderboards/jumpstats",
        params={"scope": "KZT", "type": "LJ"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 2
    assert [row["player"]["display_name"] for row in payload["data"]] == ["Alpha", "Beta"]
    assert [row["distance"] for row in payload["data"]] == [284.4444, 279.5555]
    assert payload["data"][0]["block"] == 282
    assert payload["data"][0]["strafes"] == 8
    assert payload["data"][0]["mode"] == "KZT"
    assert payload["data"][0]["type"] == "LJ"


async def test_read_jumpstat_leaderboard_defaults_to_min_rating_seven(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    players = await _seed_leaderboard_data(db)
    group, _api_key = await create_test_server_group(
        db, name="Jumpstats Threshold Leaderboard"
    )
    await _create_jumpstat(
        db,
        player_steamid64=players["beta"],
        server_group_id=group.id,
        type=JumpstatType.LJ,
        mode=KZMode.KZT,
        distance="280.0001",
        block=280,
    )

    beta_kzt_row = await db.get(LeaderboardPlayer, (ModeScope.KZT, players["beta"]))
    beta_ovr_row = await db.get(LeaderboardPlayer, (ModeScope.OVR, players["beta"]))
    assert beta_kzt_row is not None
    assert beta_ovr_row is not None
    beta_kzt_row.rating = min_raw_rating_for_public_rating(6)
    beta_ovr_row.rating = min_raw_rating_for_public_rating(6)
    await db.commit()

    default_response = await client.get(
        f"{settings.API_V1_STR}/leaderboards/jumpstats",
        params={"scope": "KZT", "type": "LJ"},
    )
    assert default_response.status_code == 200
    assert default_response.json() == {"data": [], "count": 0}

    explicit_response = await client.get(
        f"{settings.API_V1_STR}/leaderboards/jumpstats",
        params={"scope": "KZT", "type": "LJ", "min_rating": 6},
    )
    assert explicit_response.status_code == 200
    payload = explicit_response.json()
    assert payload["count"] == 1
    assert payload["data"][0]["player"]["steamid64"] == str(players["beta"])


async def test_read_jumpstat_leaderboard_rejects_invalid_min_rating(
    client: AsyncClient,
) -> None:
    response = await client.get(
        f"{settings.API_V1_STR}/leaderboards/jumpstats",
        params={"min_rating": 5},
    )

    assert response.status_code == 422


async def test_read_jumpstat_leaderboard_block_sort_uses_distance_tiebreaker(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    players = await _seed_leaderboard_data(db)
    await _set_leaderboard_rating(
        db, scope=ModeScope.OVR, steamid64=players["alpha"], rating=40_000
    )
    await _set_leaderboard_rating(
        db, scope=ModeScope.OVR, steamid64=players["beta"], rating=39_000
    )
    await _set_leaderboard_rating(
        db, scope=ModeScope.OVR, steamid64=players["gamma"], rating=38_000
    )
    group, _api_key = await create_test_server_group(db, name="Jumpstats Block Leaderboard")

    await _create_jumpstat(
        db,
        player_steamid64=players["alpha"],
        server_group_id=group.id,
        type=JumpstatType.LJ,
        mode=KZMode.KZT,
        distance="285.0000",
        block=280,
    )
    await _create_jumpstat(
        db,
        player_steamid64=players["beta"],
        server_group_id=group.id,
        type=JumpstatType.LJ,
        mode=KZMode.KZT,
        distance="282.0000",
        block=280,
    )
    await _create_jumpstat(
        db,
        player_steamid64=players["gamma"],
        server_group_id=group.id,
        type=JumpstatType.LJ,
        mode=KZMode.SKZ,
        distance="275.0000",
        block=285,
    )
    await db.commit()

    response = await client.get(
        f"{settings.API_V1_STR}/leaderboards/jumpstats",
        params={"scope": "OVR", "type": "LJ", "sort_by": "block"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 3
    assert [row["player"]["display_name"] for row in payload["data"]] == [
        "Gamma",
        "Alpha",
        "Beta",
    ]
    assert [row["block"] for row in payload["data"]] == [285, 280, 280]
    assert [row["distance"] for row in payload["data"]] == [275.0, 285.0, 282.0]


async def test_read_jumpstat_leaderboard_excludes_banned_players(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    players = await _seed_leaderboard_data(db)
    await _set_leaderboard_rating(
        db, scope=ModeScope.KZT, steamid64=players["alpha"], rating=40_000
    )
    await _set_leaderboard_rating(
        db, scope=ModeScope.KZT, steamid64=players["beta"], rating=39_000
    )
    group, _api_key = await create_test_server_group(db, name="Jumpstats Ban Leaderboard")

    await _create_jumpstat(
        db,
        player_steamid64=players["alpha"],
        server_group_id=group.id,
        type=JumpstatType.LJ,
        mode=KZMode.KZT,
        distance="286.0000",
        block=281,
    )
    await _create_jumpstat(
        db,
        player_steamid64=players["beta"],
        server_group_id=group.id,
        type=JumpstatType.LJ,
        mode=KZMode.KZT,
        distance="287.0000",
        block=282,
    )
    await _create_ban(
        db,
        ban_id=2_129_900_001,
        steamid64=players["beta"],
        expires_on=None,
    )
    await db.commit()

    response = await client.get(
        f"{settings.API_V1_STR}/leaderboards/jumpstats",
        params={"scope": "KZT", "type": "LJ"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["data"][0]["player"]["steamid64"] == str(players["alpha"])
