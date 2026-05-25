import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models import Player, PlayerSession, generate_uuid7
from tests.utils.server import create_server_group
from tests.utils.utils import random_steamid64

pytestmark = pytest.mark.asyncio


async def _create_player_session(
    db: AsyncSession,
    *,
    steamid64: int,
    group_id: uuid.UUID,
    connected_at: datetime,
    name: str,
    map_name: str,
    ip_address: str,
    geo_country: str | None = None,
    geo_region: str | None = None,
    geo_city: str | None = None,
    disconnect_after: timedelta | None = None,
) -> PlayerSession:
    player = await db.get(Player, steamid64)
    if player is None:
        player = Player(
            steamid64=steamid64,
            name=name,
            alias=f"{name} Alias",
            country="DE",
        )
        db.add(player)
        await db.commit()

    disconnect_at = (
        connected_at + disconnect_after if disconnect_after is not None else None
    )
    player_session = PlayerSession(
        id=generate_uuid7(timestamp=connected_at),
        player_steamid64=steamid64,
        server_group_id=group_id,
        connected_at=connected_at,
        disconnect_at=disconnect_at,
        last_heartbeat_at=disconnect_at or connected_at + timedelta(minutes=5),
        ip_address=ip_address,
        geo_country=geo_country,
        geo_region=geo_region,
        geo_city=geo_city,
        map_name=map_name,
    )
    db.add(player_session)
    await db.commit()
    await db.refresh(player_session)
    return player_session


async def test_admin_player_sessions_require_superuser(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    admin_auth = await client.post(
        f"{settings.API_V1_STR}/private/auth/session",
        json={
            "steamid64": random_steamid64(),
            "roles": ["admin"],
            "is_active": True,
            "name": "Admin Player Session Tester",
        },
    )
    admin_headers = {"Authorization": f"Bearer {admin_auth.json()['access_token']}"}
    unauthenticated_response = await client.get(
        f"{settings.API_V1_STR}/admin/player-sessions"
    )
    normal_user_response = await client.get(
        f"{settings.API_V1_STR}/admin/player-sessions",
        headers=normal_user_token_headers,
    )
    admin_response = await client.get(
        f"{settings.API_V1_STR}/admin/player-sessions",
        headers=admin_headers,
    )

    assert unauthenticated_response.status_code in {401, 403}
    assert normal_user_response.status_code == 403
    assert admin_response.status_code == 403


async def test_read_admin_player_sessions_lists_paginates_and_sorts(
    client: AsyncClient,
    db: AsyncSession,
    superuser_token_headers: dict[str, str],
) -> None:
    group, _api_key = await create_server_group(db, name="Session Group")
    first_steamid64 = random_steamid64()
    second_steamid64 = random_steamid64()
    first_time = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)
    second_time = datetime(2026, 4, 28, 13, 0, tzinfo=UTC)
    third_time = datetime(2026, 4, 28, 14, 0, tzinfo=UTC)
    await _create_player_session(
        db,
        steamid64=first_steamid64,
        group_id=group.id,
        connected_at=first_time,
        name="Alpha",
        map_name="kz_alpha",
        ip_address="127.0.0.10",
        disconnect_after=timedelta(minutes=10),
    )
    await _create_player_session(
        db,
        steamid64=second_steamid64,
        group_id=group.id,
        connected_at=second_time,
        name="Bravo",
        map_name="kz_bravo",
        ip_address="127.0.0.11",
    )
    newest = await _create_player_session(
        db,
        steamid64=first_steamid64,
        group_id=group.id,
        connected_at=third_time,
        name="Alpha",
        map_name="kz_newest",
        ip_address="127.0.0.12",
        disconnect_after=timedelta(minutes=30),
    )

    response = await client.get(
        f"{settings.API_V1_STR}/admin/player-sessions",
        headers=superuser_token_headers,
        params={"offset": 0, "limit": 2},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 3
    assert [row["map_name"] for row in payload["data"]] == ["kz_newest", "kz_bravo"]
    assert payload["data"][0]["id"] == str(newest.id)
    assert payload["data"][0]["player"]["steamid64"] == str(first_steamid64)
    assert payload["data"][0]["player"]["alias"] == "Alpha Alias"
    assert payload["data"][0]["server_group_id"] == str(group.id)
    assert payload["data"][0]["server_group_name"] == "Session Group"
    assert payload["data"][0]["ip_address"] == "127.0.0.12"
    assert payload["data"][0]["duration_seconds"] == 1800


async def test_read_admin_player_sessions_latest_only_returns_newest_per_player(
    client: AsyncClient,
    db: AsyncSession,
    superuser_token_headers: dict[str, str],
) -> None:
    group, _api_key = await create_server_group(db, name="Latest Group")
    first_steamid64 = random_steamid64()
    second_steamid64 = random_steamid64()
    older_time = datetime(2026, 4, 28, 10, 0, tzinfo=UTC)
    newest_time = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)
    other_time = datetime(2026, 4, 28, 11, 0, tzinfo=UTC)
    await _create_player_session(
        db,
        steamid64=first_steamid64,
        group_id=group.id,
        connected_at=older_time,
        name="Alpha",
        map_name="kz_old",
        ip_address="127.0.0.20",
    )
    newest = await _create_player_session(
        db,
        steamid64=first_steamid64,
        group_id=group.id,
        connected_at=newest_time,
        name="Alpha",
        map_name="kz_latest",
        ip_address="127.0.0.21",
    )
    other = await _create_player_session(
        db,
        steamid64=second_steamid64,
        group_id=group.id,
        connected_at=other_time,
        name="Bravo",
        map_name="kz_other",
        ip_address="127.0.0.22",
    )

    response = await client.get(
        f"{settings.API_V1_STR}/admin/player-sessions",
        headers=superuser_token_headers,
        params={"latest_only": "true", "limit": 100},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 2
    assert [row["id"] for row in payload["data"]] == [str(newest.id), str(other.id)]
    assert [row["map_name"] for row in payload["data"]] == ["kz_latest", "kz_other"]


async def test_admin_player_session_ip_links_require_superuser(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    unauthenticated_response = await client.get(
        f"{settings.API_V1_STR}/admin/player-sessions/ip-links",
        params={"steamid64": str(random_steamid64())},
    )
    normal_user_response = await client.get(
        f"{settings.API_V1_STR}/admin/player-sessions/ip-links",
        headers=normal_user_token_headers,
        params={"steamid64": str(random_steamid64())},
    )

    assert unauthenticated_response.status_code in {401, 403}
    assert normal_user_response.status_code == 403


async def test_admin_player_session_ip_links_exact_ip_depth_one(
    client: AsyncClient,
    db: AsyncSession,
    superuser_token_headers: dict[str, str],
) -> None:
    group, _api_key = await create_server_group(db, name="Alt Group")
    target = random_steamid64()
    linked = random_steamid64()
    unrelated = random_steamid64()
    connected_at = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)
    await _create_player_session(
        db,
        steamid64=target,
        group_id=group.id,
        connected_at=connected_at,
        name="Target",
        map_name="kz_target",
        ip_address="8.8.8.8",
    )
    await _create_player_session(
        db,
        steamid64=linked,
        group_id=group.id,
        connected_at=connected_at + timedelta(minutes=5),
        name="Linked",
        map_name="kz_linked",
        ip_address="8.8.8.8",
    )
    await _create_player_session(
        db,
        steamid64=unrelated,
        group_id=group.id,
        connected_at=connected_at + timedelta(minutes=10),
        name="Unrelated",
        map_name="kz_unrelated",
        ip_address="8.8.4.4",
    )

    response = await client.get(
        f"{settings.API_V1_STR}/admin/player-sessions/ip-links",
        headers=superuser_token_headers,
        params={
            "steamid64": str(target),
            "match_mode": "exact_ip",
            "depth": 1,
            "days": 365,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["target"]["steamid64"] == str(target)
    assert [row["player"]["steamid64"] for row in payload["players"]] == [
        str(target),
        str(linked),
    ]
    assert payload["players"][1]["distance"] == 1
    assert payload["links"][0]["bucket"]["label"] == "8.8.8.8"
    assert payload["skipped_buckets"] == []


async def test_admin_player_session_ip_links_depth_two_avoids_loops(
    client: AsyncClient,
    db: AsyncSession,
    superuser_token_headers: dict[str, str],
) -> None:
    group, _api_key = await create_server_group(db, name="Depth Group")
    target = random_steamid64()
    first_hop = random_steamid64()
    second_hop = random_steamid64()
    connected_at = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)
    await _create_player_session(
        db,
        steamid64=target,
        group_id=group.id,
        connected_at=connected_at,
        name="Target",
        map_name="kz_target",
        ip_address="8.8.8.8",
    )
    await _create_player_session(
        db,
        steamid64=first_hop,
        group_id=group.id,
        connected_at=connected_at + timedelta(minutes=1),
        name="First",
        map_name="kz_first",
        ip_address="8.8.8.8",
    )
    await _create_player_session(
        db,
        steamid64=first_hop,
        group_id=group.id,
        connected_at=connected_at + timedelta(minutes=2),
        name="First",
        map_name="kz_first_next",
        ip_address="1.1.1.1",
    )
    await _create_player_session(
        db,
        steamid64=second_hop,
        group_id=group.id,
        connected_at=connected_at + timedelta(minutes=3),
        name="Second",
        map_name="kz_second",
        ip_address="1.1.1.1",
    )

    response = await client.get(
        f"{settings.API_V1_STR}/admin/player-sessions/ip-links",
        headers=superuser_token_headers,
        params={"steamid64": str(target), "depth": 2},
    )

    assert response.status_code == 200
    payload = response.json()
    distances = {
        row["player"]["steamid64"]: row["distance"] for row in payload["players"]
    }
    assert distances == {
        str(target): 0,
        str(first_hop): 1,
        str(second_hop): 2,
    }
    assert len(payload["links"]) == 2


async def test_admin_player_session_ip_links_same_24(
    client: AsyncClient,
    db: AsyncSession,
    superuser_token_headers: dict[str, str],
) -> None:
    group, _api_key = await create_server_group(db, name="Prefix Group")
    target = random_steamid64()
    linked = random_steamid64()
    connected_at = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)
    await _create_player_session(
        db,
        steamid64=target,
        group_id=group.id,
        connected_at=connected_at,
        name="Target",
        map_name="kz_target",
        ip_address="8.8.8.8",
    )
    await _create_player_session(
        db,
        steamid64=linked,
        group_id=group.id,
        connected_at=connected_at + timedelta(minutes=1),
        name="Linked",
        map_name="kz_linked",
        ip_address="8.8.8.9",
    )

    response = await client.get(
        f"{settings.API_V1_STR}/admin/player-sessions/ip-links",
        headers=superuser_token_headers,
        params={"steamid64": str(target), "match_mode": "same_24"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert [row["player"]["steamid64"] for row in payload["players"]] == [
        str(target),
        str(linked),
    ]
    assert payload["links"][0]["bucket"]["ip_prefix"] == "8.8.8.0/24"


async def test_admin_player_session_ip_links_same_16_city_requires_geo_match(
    client: AsyncClient,
    db: AsyncSession,
    superuser_token_headers: dict[str, str],
) -> None:
    group, _api_key = await create_server_group(db, name="Geo Group")
    target = random_steamid64()
    linked = random_steamid64()
    different_city = random_steamid64()
    connected_at = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)
    await _create_player_session(
        db,
        steamid64=target,
        group_id=group.id,
        connected_at=connected_at,
        name="Target",
        map_name="kz_target",
        ip_address="8.8.1.1",
        geo_country="US",
        geo_region="Illinois",
        geo_city="Chicago",
    )
    await _create_player_session(
        db,
        steamid64=linked,
        group_id=group.id,
        connected_at=connected_at + timedelta(minutes=1),
        name="Linked",
        map_name="kz_linked",
        ip_address="8.8.2.2",
        geo_country="US",
        geo_region="Illinois",
        geo_city="Chicago",
    )
    await _create_player_session(
        db,
        steamid64=different_city,
        group_id=group.id,
        connected_at=connected_at + timedelta(minutes=2),
        name="Other",
        map_name="kz_other",
        ip_address="8.8.3.3",
        geo_country="US",
        geo_region="Illinois",
        geo_city="Springfield",
    )

    response = await client.get(
        f"{settings.API_V1_STR}/admin/player-sessions/ip-links",
        headers=superuser_token_headers,
        params={"steamid64": str(target), "match_mode": "same_16_city"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert [row["player"]["steamid64"] for row in payload["players"]] == [
        str(target),
        str(linked),
    ]
    assert payload["links"][0]["bucket"]["ip_prefix"] == "8.8.0.0/16"
    assert payload["links"][0]["bucket"]["geo_city"] == "Chicago"


async def test_admin_player_session_ip_links_time_range_and_busy_bucket(
    client: AsyncClient,
    db: AsyncSession,
    superuser_token_headers: dict[str, str],
) -> None:
    group, _api_key = await create_server_group(db, name="Busy Group")
    target = random_steamid64()
    linked = random_steamid64()
    old_linked = random_steamid64()
    connected_at = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)
    await _create_player_session(
        db,
        steamid64=target,
        group_id=group.id,
        connected_at=connected_at,
        name="Target",
        map_name="kz_target",
        ip_address="8.8.8.8",
    )
    await _create_player_session(
        db,
        steamid64=linked,
        group_id=group.id,
        connected_at=connected_at + timedelta(minutes=1),
        name="Linked",
        map_name="kz_linked",
        ip_address="8.8.8.8",
    )
    await _create_player_session(
        db,
        steamid64=old_linked,
        group_id=group.id,
        connected_at=connected_at - timedelta(days=400),
        name="Old",
        map_name="kz_old",
        ip_address="8.8.8.8",
    )

    time_range_response = await client.get(
        f"{settings.API_V1_STR}/admin/player-sessions/ip-links",
        headers=superuser_token_headers,
        params={"steamid64": str(target), "days": 365},
    )
    busy_response = await client.get(
        f"{settings.API_V1_STR}/admin/player-sessions/ip-links",
        headers=superuser_token_headers,
        params={
            "steamid64": str(target),
            "days": 365,
            "max_players_per_bucket": 1,
        },
    )

    assert time_range_response.status_code == 200
    assert [
        row["player"]["steamid64"] for row in time_range_response.json()["players"]
    ] == [str(target), str(linked)]
    assert busy_response.status_code == 200
    busy_payload = busy_response.json()
    assert [row["player"]["steamid64"] for row in busy_payload["players"]] == [
        str(target)
    ]
    assert busy_payload["links"] == []
    assert busy_payload["skipped_buckets"][0]["bucket"]["label"] == "8.8.8.8"
    assert busy_payload["skipped_buckets"][0]["player_count"] == 2


async def test_admin_player_session_ip_links_invalid_query(
    client: AsyncClient,
    superuser_token_headers: dict[str, str],
) -> None:
    response = await client.get(
        f"{settings.API_V1_STR}/admin/player-sessions/ip-links",
        headers=superuser_token_headers,
        params={"steamid64": "not-a-steamid", "depth": 6},
    )

    assert response.status_code == 422
