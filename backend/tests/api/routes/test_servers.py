import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.api.v1 import servers as servers_route
from app.core.config import settings
from app.crud import server as server_crud
from app.models import (
    KZMode,
    LeaderboardPlayer,
    Map,
    ModeScope,
    Player,
    Record,
    ServerGlobalapi,
    ServerGroup,
    ServerGroupStatus,
    ServerGroupUpdate,
    ServerStatus,
    ServerStatusPut,
)
from app.models.leaderboard_player import scale_public_rating
from app.services.geoip import GeoIPLocation
from app.services.server_status import (
    A2SInfoResult,
    ServerQueryError,
)
from tests.utils.server import (
    create_server,
    create_server_group,
    random_server_ip,
    random_server_port,
)

pytestmark = pytest.mark.asyncio


async def _create_map(
    db: AsyncSession,
    *,
    id: int,
    name: str,
    difficulty: int,
) -> Map:
    map_obj = Map(
        id=id,
        name=name,
        filesize=123456,
        validated=True,
        difficulty=difficulty,
        created_on=datetime(2021, 1, 1, tzinfo=UTC),
        updated_on=datetime(2021, 1, 2, tzinfo=UTC),
        approved_by_steamid64=76561198003275951,
        workshop_id=1986459033,
        authors=["76561198000000001"],
        no_steamid_names=["Unknown Mapper"],
        synced_at=datetime(2021, 1, 3, tzinfo=UTC),
    )
    db.add(map_obj)
    await db.commit()
    await db.refresh(map_obj)
    return map_obj


async def _create_activity_player(
    db: AsyncSession,
    *,
    steamid64: int,
    custom_id: str | None = None,
    primary_scope: ModeScope = ModeScope.KZT,
) -> Player:
    player = Player(
        steamid64=steamid64,
        name=f"Player {steamid64}",
        custom_id=custom_id,
        primary_scope=primary_scope,
    )
    db.add(player)
    await db.commit()
    await db.refresh(player)
    return player


async def _create_activity_group(
    db: AsyncSession,
    *,
    custom_id: str,
    name: str,
) -> ServerGroup:
    group, _api_key = await create_server_group(db, name=name)
    group = await crud.update_server_group(
        session=db,
        group=group,
        group_in=ServerGroupUpdate(custom_id=custom_id),
    )
    return group


async def _create_activity_globalapi_server(
    db: AsyncSession,
    *,
    id: int,
    group_id: uuid.UUID,
    name: str,
) -> ServerGlobalapi:
    server = ServerGlobalapi(
        id=id,
        port=27015,
        ip=f"203.0.113.{id % 255}",
        name=name,
        group_id=group_id,
        owner_steamid64=None,
        approval_status=1,
        approved_by_steamid64=None,
    )
    db.add(server)
    await db.commit()
    await db.refresh(server)
    return server


async def _create_activity_record(
    db: AsyncSession,
    *,
    id: int,
    steamid64: int,
    server_id: int,
    map_id: int,
    created_at: datetime,
    time_seconds: str,
    is_valid: bool = True,
) -> Record:
    record = Record(
        id=id,
        steamid64=steamid64,
        server_id=server_id,
        mode=KZMode.KZT,
        map_id=map_id,
        stage=0,
        time=Decimal(time_seconds),
        teleports=1,
        points=0,
        created_at=created_at,
        updated_at=created_at,
        updated_by=steamid64,
        is_valid=is_valid,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


def _activity_summary_url(
    *,
    server_id: str,
    identifier: str,
    recent_hours: int = 50,
) -> str:
    return (
        f"{settings.API_V1_STR}/servers/{server_id}/players/{identifier}"
        f"/activity-summary?recent_hours={recent_hours}"
    )


def _plugin_player(
    *,
    name: str = "Player One",
    steamid64: str = "76561198000000001",
    status: str = "in_progress",
) -> dict[str, object]:
    return {
        "tag": "RANK 1",
        "mode": "KZT",
        "name": name,
        "score": 7,
        "status": status,
        "duration_seconds": 125.5,
        "is_paused": False,
        "steamid64": steamid64,
        "teleports": 3,
        "timer_time": 32.75,
        "stage": 0,
    }


def _async_location(
    location: GeoIPLocation | None,
) -> Callable[[str], Awaitable[GeoIPLocation | None]]:
    async def _lookup_ip_location(_ip: str) -> GeoIPLocation | None:
        return location

    return _lookup_ip_location


async def test_read_player_server_activity_summary_uses_record_playtime_window(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    steamid64 = 76561198000050101
    generated_at = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(servers_route, "get_datetime_utc", lambda: generated_at)
    player = await _create_activity_player(db, steamid64=steamid64)
    target_group = await _create_activity_group(
        db,
        custom_id="axe-gokz",
        name="AXE GOKZ",
    )
    other_group = await _create_activity_group(
        db,
        custom_id="other-kz",
        name="Other KZ",
    )
    await _create_map(db, id=990101, name="kz_activity_summary", difficulty=4)
    target_server = await _create_activity_globalapi_server(
        db,
        id=990201,
        group_id=target_group.id,
        name="AXE Server",
    )
    other_server = await _create_activity_globalapi_server(
        db,
        id=990202,
        group_id=other_group.id,
        name="Other Server",
    )
    raw_rating = 30000
    db.add(
        LeaderboardPlayer(
            scope=ModeScope.KZT,
            steamid64=steamid64,
            rating=raw_rating,
        )
    )
    await db.commit()
    await db.refresh(player)

    await _create_activity_record(
        db,
        id=990301,
        steamid64=steamid64,
        server_id=target_server.id,
        map_id=990101,
        created_at=datetime(2026, 3, 23, 18, 22, 11, tzinfo=UTC),
        time_seconds="1000.000",
        is_valid=False,
    )
    await _create_activity_record(
        db,
        id=990302,
        steamid64=steamid64,
        server_id=other_server.id,
        map_id=990101,
        created_at=datetime(2026, 3, 24, 18, 22, 11, tzinfo=UTC),
        time_seconds="2000.000",
    )
    await _create_activity_record(
        db,
        id=990303,
        steamid64=steamid64,
        server_id=target_server.id,
        map_id=990101,
        created_at=datetime(2026, 3, 25, 18, 22, 11, tzinfo=UTC),
        time_seconds="2000.000",
    )

    response = await client.get(
        _activity_summary_url(
            server_id="AXE-GOKZ",
            identifier=str(steamid64),
            recent_hours=1,
        )
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "steam_id": str(steamid64),
        "server_id": "axe-gokz",
        "generated_at": "2026-07-20T12:00:00Z",
        "ratings": [
            {
                "mode": "KZT",
                "rating": scale_public_rating(raw_rating),
                "is_primary": True,
            }
        ],
        "activity": {
            "first_seen_at": "2026-03-23T18:22:11Z",
            "first_server_record_at": "2026-03-23T18:22:11Z",
            "active_days": 3,
            "total_playtime_seconds": 5000.0,
            "recent_playtime": {
                "requested_hours": 1,
                "window_seconds": 3600.0,
                "on_server_seconds": 2000.0,
                "ratio": 0.556,
            },
        },
    }


async def test_read_player_server_activity_summary_uses_short_record_history(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    steamid64 = 76561198000050102
    await _create_activity_player(
        db,
        steamid64=steamid64,
        custom_id="short-runner",
    )
    target_group = await _create_activity_group(
        db,
        custom_id="short-kz",
        name="Short KZ",
    )
    await _create_map(db, id=990102, name="kz_short_summary", difficulty=3)
    target_server = await _create_activity_globalapi_server(
        db,
        id=990203,
        group_id=target_group.id,
        name="Short Server",
    )
    await _create_activity_record(
        db,
        id=990304,
        steamid64=steamid64,
        server_id=target_server.id,
        map_id=990102,
        created_at=datetime(2026, 4, 1, 12, 0, tzinfo=UTC),
        time_seconds="1200.000",
    )

    response = await client.get(
        _activity_summary_url(
            server_id="short-kz",
            identifier="short-runner",
            recent_hours=1,
        )
    )

    assert response.status_code == 200
    activity = response.json()["activity"]
    assert activity["first_server_record_at"] == "2026-04-01T12:00:00Z"
    recent_playtime = activity["recent_playtime"]
    assert recent_playtime == {
        "requested_hours": 1,
        "window_seconds": 1200.0,
        "on_server_seconds": 1200.0,
        "ratio": 1.0,
    }


async def test_read_player_server_activity_summary_returns_not_found_for_missing_group(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    steamid64 = 76561198000050103
    await _create_activity_player(db, steamid64=steamid64)

    response = await client.get(
        _activity_summary_url(
            server_id="missing-kz",
            identifier=str(steamid64),
        )
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Server group not found"


async def test_read_player_server_activity_summary_returns_not_found_for_missing_player(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    await _create_activity_group(
        db,
        custom_id="known-kz",
        name="Known KZ",
    )

    response = await client.get(
        _activity_summary_url(
            server_id="known-kz",
            identifier="76561198000050104",
        )
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Player not found"


async def test_read_player_server_activity_summary_returns_not_found_for_unknown_identifier(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    await _create_activity_group(
        db,
        custom_id="axe-gokz",
        name="AXE GOKZ",
    )

    response = await client.get(
        _activity_summary_url(
            server_id="axe-gokz",
            identifier="not-a-steamid",
        )
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Player not found"


async def test_create_server_requires_successful_a2s_query(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_query_server_a2s_info(*, ip: str, port: int) -> A2SInfoResult:
        return A2SInfoResult(
            hostname=f"Queried {ip}:{port}",
            map_name="kz_alpha",
            player_count=3,
            max_players=24,
            players=[],
            observed_at=datetime.now(UTC),
            game_directory="csgo",
            app_id=730,
        )

    monkeypatch.setattr(
        servers_route, "query_server_a2s_info", _fake_query_server_a2s_info
    )
    monkeypatch.setattr(
        server_crud,
        "lookup_ip_location",
        _async_location(
            GeoIPLocation(
                country_code="US",
                city_name="Chicago",
                latitude=41.8781,
                longitude=-87.6298,
            )
        ),
    )

    response = await client.post(
        f"{settings.API_V1_STR}/servers",
        headers=normal_user_token_headers,
        json={
            "ip": random_server_ip(),
            "port": random_server_port(),
            "status": "enabled",
            "country": "DE",
            "city": "Berlin",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "enabled"
    assert payload["source"]["type"] == "manual"
    assert payload["source"]["steamid64"].isdigit()
    assert payload["live_status"]["hostname"].startswith("Queried ")
    assert payload["live_status"]["map"] == "kz_alpha"
    assert payload["country"] == "DE"
    assert payload["region"] == "EU"
    assert payload["city"] == "Berlin"


async def test_create_server_fills_blank_location_from_geoip(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_query_server_a2s_info(*, ip: str, port: int) -> A2SInfoResult:
        del ip, port
        return A2SInfoResult(
            hostname="Queried Host",
            map_name="kz_geoip",
            player_count=3,
            max_players=24,
            players=[],
            observed_at=datetime.now(UTC),
            game_directory="csgo",
            app_id=730,
        )

    monkeypatch.setattr(
        servers_route, "query_server_a2s_info", _fake_query_server_a2s_info
    )
    monkeypatch.setattr(
        server_crud,
        "lookup_ip_location",
        _async_location(
            GeoIPLocation(
                country_code="US",
                city_name="Chicago",
                latitude=41.8781,
                longitude=-87.6298,
            )
        ),
    )

    response = await client.post(
        f"{settings.API_V1_STR}/servers",
        headers=normal_user_token_headers,
        json={
            "ip": random_server_ip(),
            "port": random_server_port(),
            "status": "enabled",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["country"] == "US"
    assert payload["region"] == "NA"
    assert payload["city"] == "Chicago"
    assert payload["latitude"] == 41.8781
    assert payload["longitude"] == -87.6298


async def test_create_server_rejects_out_of_range_coordinates(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    response = await client.post(
        f"{settings.API_V1_STR}/servers",
        headers=normal_user_token_headers,
        json={
            "ip": random_server_ip(),
            "port": random_server_port(),
            "latitude": 91,
            "longitude": -181,
        },
    )

    assert response.status_code == 422


async def test_read_servers_returns_derived_region_and_filters_by_region(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    eu_server = await create_server(db, country="DE", city="Berlin")
    await create_server(db, country="US", city="Chicago")

    response = await client.get(
        f"{settings.API_V1_STR}/servers",
        params={"region": "EU", "limit": 200},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["data"][0]["id"] == str(eu_server.id)
    assert payload["data"][0]["region"] == "EU"


async def test_read_servers_returns_group_custom_id(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    group, _ = await create_server_group(db)
    group = await crud.update_server_group(
        session=db,
        group=group,
        group_in=ServerGroupUpdate(custom_id="axe"),
    )
    server = await create_server(db, group_id=group.id)

    response = await client.get(
        f"{settings.API_V1_STR}/servers",
        params={"limit": 200},
    )

    assert response.status_code == 200
    payload = response.json()
    [server_payload] = [
        item for item in payload["data"] if item["id"] == str(server.id)
    ]
    assert server_payload["group"] == {
        "id": str(group.id),
        "name": group.name,
        "custom_id": "axe",
    }


async def test_read_servers_returns_persisted_coordinates(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = await create_server(db, latitude=52.52, longitude=13.405)

    async def _unexpected_lookup_ip_location(_ip: str) -> GeoIPLocation | None:
        raise AssertionError("Public server reads must use persisted coordinates")

    monkeypatch.setattr(
        server_crud,
        "lookup_ip_location",
        _unexpected_lookup_ip_location,
    )

    response = await client.get(
        f"{settings.API_V1_STR}/servers",
        params={"limit": 200},
    )

    assert response.status_code == 200
    payload = response.json()
    [server_payload] = [
        item for item in payload["data"] if item["id"] == str(server.id)
    ]
    assert server_payload["latitude"] == 52.52
    assert server_payload["longitude"] == 13.405


async def test_read_servers_returns_null_coordinates_without_geoip_location(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = await create_server(db)
    monkeypatch.setattr(server_crud, "lookup_ip_location", _async_location(None))

    response = await client.get(
        f"{settings.API_V1_STR}/servers",
        params={"limit": 200},
    )

    assert response.status_code == 200
    payload = response.json()
    [server_payload] = [
        item for item in payload["data"] if item["id"] == str(server.id)
    ]
    assert server_payload["latitude"] is None
    assert server_payload["longitude"] is None


async def test_read_servers_accepts_limit_1000(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    await create_server(db)

    response = await client.get(
        f"{settings.API_V1_STR}/servers",
        params={"limit": 1000},
    )

    assert response.status_code == 200


async def test_read_servers_rejects_limit_above_1000(
    client: AsyncClient,
) -> None:
    response = await client.get(
        f"{settings.API_V1_STR}/servers",
        params={"limit": 1001},
    )

    assert response.status_code == 422


async def test_create_server_reenables_existing_invalid_server(
    client: AsyncClient,
    db: AsyncSession,
    normal_user_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = await create_server(db, hostname="Old Host", map_name="kz_old")
    server.status = ServerStatus.INVALID
    db.add(server)
    await db.commit()

    async def _fake_query_server_a2s_info(*, ip: str, port: int) -> A2SInfoResult:
        assert ip == server.ip
        assert port == server.port
        return A2SInfoResult(
            hostname="Recovered Host",
            map_name="kz_recovered",
            player_count=4,
            max_players=24,
            players=[],
            observed_at=datetime.now(UTC),
            game_directory="csgo",
            app_id=730,
        )

    monkeypatch.setattr(
        servers_route, "query_server_a2s_info", _fake_query_server_a2s_info
    )

    response = await client.post(
        f"{settings.API_V1_STR}/servers",
        headers=normal_user_token_headers,
        json={"ip": server.ip, "port": server.port},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == str(server.id)
    assert payload["status"] == "enabled"
    assert payload["source"]["type"] == "manual"
    assert payload["live_status"]["hostname"] == "Recovered Host"
    assert payload["live_status"]["map"] == "kz_recovered"


async def test_create_server_rejects_existing_disabled_server(
    client: AsyncClient,
    db: AsyncSession,
    normal_user_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = await create_server(db, hostname="Disabled Host")
    server.status = ServerStatus.DISABLED
    db.add(server)
    await db.commit()

    async def _fake_query_server_a2s_info(*, ip: str, port: int) -> A2SInfoResult:
        assert ip == server.ip
        assert port == server.port
        return A2SInfoResult(
            hostname="Recovered Host",
            map_name="kz_recovered",
            player_count=4,
            max_players=24,
            players=[],
            observed_at=datetime.now(UTC),
            game_directory="csgo",
            app_id=730,
        )

    monkeypatch.setattr(
        servers_route, "query_server_a2s_info", _fake_query_server_a2s_info
    )

    response = await client.post(
        f"{settings.API_V1_STR}/servers",
        headers=normal_user_token_headers,
        json={"ip": server.ip, "port": server.port},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Server is disabled"


async def test_trigger_server_discovery_requires_superuser(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    response = await client.post(
        f"{settings.API_V1_STR}/admin/server-discovery-runs",
        headers=normal_user_token_headers,
    )

    assert response.status_code == 403


async def test_trigger_server_discovery_returns_disabled_when_feature_flag_is_off(
    client: AsyncClient,
    superuser_token_headers: dict[str, str],
) -> None:
    response = await client.post(
        f"{settings.API_V1_STR}/admin/server-discovery-runs",
        headers=superuser_token_headers,
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Server discovery is temporarily disabled"


async def test_create_server_rejects_unreachable_server(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _failing_query_server_a2s_info(*, ip: str, port: int) -> A2SInfoResult:
        raise ServerQueryError(f"unreachable {ip}:{port}")

    monkeypatch.setattr(
        servers_route,
        "query_server_a2s_info",
        _failing_query_server_a2s_info,
    )

    response = await client.post(
        f"{settings.API_V1_STR}/servers",
        headers=normal_user_token_headers,
        json={"ip": random_server_ip(), "port": random_server_port()},
    )

    assert response.status_code == 422
    assert response.json()["detail"].startswith("unreachable ")


async def test_create_server_rejects_non_csgo_server(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_query_server_a2s_info(*, ip: str, port: int) -> A2SInfoResult:
        del ip, port
        return A2SInfoResult(
            hostname="Surf Server",
            map_name="kz_alpha",
            player_count=12,
            max_players=24,
            players=[],
            observed_at=datetime.now(UTC),
            game_directory="tf",
            game_name="Team Fortress",
            app_id=440,
        )

    monkeypatch.setattr(
        servers_route,
        "query_server_a2s_info",
        _fake_query_server_a2s_info,
    )

    response = await client.post(
        f"{settings.API_V1_STR}/servers",
        headers=normal_user_token_headers,
        json={"ip": random_server_ip(), "port": random_server_port()},
    )

    assert response.status_code == 422
    assert (
        response.json()["detail"]
        == "Server is running game 'Team Fortress', expected Counter-Strike: Global Offensive"
    )


async def test_create_server_rejects_counter_strike_2_even_when_folder_and_app_id_match(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_query_server_a2s_info(*, ip: str, port: int) -> A2SInfoResult:
        return A2SInfoResult(
            hostname=f"Queried {ip}:{port}",
            map_name="kz_alpha",
            player_count=3,
            max_players=24,
            players=[],
            observed_at=datetime.now(UTC),
            game_directory="csgo",
            game_name="Counter-Strike 2",
            app_id=730,
        )

    monkeypatch.setattr(
        servers_route,
        "query_server_a2s_info",
        _fake_query_server_a2s_info,
    )
    monkeypatch.setattr(
        server_crud,
        "lookup_ip_location",
        _async_location(GeoIPLocation(country_code="US", city_name="Chicago")),
    )

    response = await client.post(
        f"{settings.API_V1_STR}/servers",
        headers=normal_user_token_headers,
        json={"ip": random_server_ip(), "port": random_server_port()},
    )

    assert response.status_code == 422
    assert (
        response.json()["detail"]
        == "Server is running game 'Counter-Strike 2', expected Counter-Strike: Global Offensive"
    )


async def test_create_server_allows_zero_app_id_when_game_field_matches_csgo(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_query_server_a2s_info(*, ip: str, port: int) -> A2SInfoResult:
        return A2SInfoResult(
            hostname=f"Queried {ip}:{port}",
            map_name="kz_alpha",
            player_count=3,
            max_players=24,
            players=[],
            observed_at=datetime.now(UTC),
            game_directory="",
            game_name="Counter-Strike: Global Offensive",
            app_id=0,
        )

    monkeypatch.setattr(
        servers_route,
        "query_server_a2s_info",
        _fake_query_server_a2s_info,
    )
    monkeypatch.setattr(
        server_crud,
        "lookup_ip_location",
        _async_location(GeoIPLocation(country_code="US", city_name="Chicago")),
    )

    response = await client.post(
        f"{settings.API_V1_STR}/servers",
        headers=normal_user_token_headers,
        json={"ip": random_server_ip(), "port": random_server_port()},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["live_status"]["hostname"].startswith("Queried ")


async def test_create_server_rejects_non_kz_map(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_query_server_a2s_info(*, ip: str, port: int) -> A2SInfoResult:
        del ip, port
        return A2SInfoResult(
            hostname="Pug Server",
            map_name="de_dust2",
            player_count=12,
            max_players=24,
            players=[],
            observed_at=datetime.now(UTC),
            game_directory="csgo",
            game_name="Counter-Strike: Global Offensive",
            app_id=730,
        )

    monkeypatch.setattr(
        servers_route,
        "query_server_a2s_info",
        _fake_query_server_a2s_info,
    )

    response = await client.post(
        f"{settings.API_V1_STR}/servers",
        headers=normal_user_token_headers,
        json={"ip": random_server_ip(), "port": random_server_port()},
    )

    assert response.status_code == 422
    assert (
        response.json()["detail"]
        == "Server is running map 'de_dust2', expected one of kz_*, bkz_*, vnl_*, skz_*, xc_*, kzpro_*"
    )


async def test_update_server_requeries_when_endpoint_changes(
    client: AsyncClient,
    db: AsyncSession,
    superuser_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = await create_server(db, hostname="Original Host", map_name="kz_old")

    async def _fake_query_server_a2s_info(*, ip: str, port: int) -> A2SInfoResult:
        del ip, port
        return A2SInfoResult(
            hostname="Updated Host",
            map_name="kz_new",
            player_count=7,
            max_players=32,
            players=[],
            observed_at=datetime.now(UTC),
        )

    monkeypatch.setattr(
        servers_route, "query_server_a2s_info", _fake_query_server_a2s_info
    )

    response = await client.patch(
        f"{settings.API_V1_STR}/servers/{server.id}",
        headers=superuser_token_headers,
        json={"ip": random_server_ip(), "port": random_server_port()},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["live_status"]["hostname"] == "Updated Host"
    assert payload["live_status"]["map"] == "kz_new"


async def test_update_server_fills_missing_location_from_geoip(
    client: AsyncClient,
    db: AsyncSession,
    superuser_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = await create_server(db, country=None, city=None)
    monkeypatch.setattr(
        server_crud,
        "lookup_ip_location",
        _async_location(GeoIPLocation(country_code="US", city_name="Chicago")),
    )

    response = await client.patch(
        f"{settings.API_V1_STR}/servers/{server.id}",
        headers=superuser_token_headers,
        json={"status": "enabled"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["country"] == "US"
    assert payload["city"] == "Chicago"


async def test_update_server_refreshes_location_when_ip_changes(
    client: AsyncClient,
    db: AsyncSession,
    superuser_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = await create_server(
        db,
        country="DE",
        city="Berlin",
        latitude=52.52,
        longitude=13.405,
    )

    async def _fake_query_server_a2s_info(*, ip: str, port: int) -> A2SInfoResult:
        del ip, port
        return A2SInfoResult(
            hostname="Updated Host",
            map_name="kz_new",
            player_count=7,
            max_players=32,
            players=[],
            observed_at=datetime.now(UTC),
        )

    monkeypatch.setattr(
        servers_route, "query_server_a2s_info", _fake_query_server_a2s_info
    )
    monkeypatch.setattr(
        server_crud,
        "lookup_ip_location",
        _async_location(
            GeoIPLocation(
                country_code="US",
                city_name="Chicago",
                latitude=41.8781,
                longitude=-87.6298,
            )
        ),
    )

    response = await client.patch(
        f"{settings.API_V1_STR}/servers/{server.id}",
        headers=superuser_token_headers,
        json={"ip": random_server_ip()},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["country"] == "US"
    assert payload["city"] == "Chicago"
    assert payload["latitude"] == 41.8781
    assert payload["longitude"] == -87.6298


async def test_update_server_preserves_existing_location_values(
    client: AsyncClient,
    db: AsyncSession,
    superuser_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = await create_server(db, country="DE", city="Berlin")
    monkeypatch.setattr(
        server_crud,
        "lookup_ip_location",
        _async_location(GeoIPLocation(country_code="US", city_name="Chicago")),
    )

    response = await client.patch(
        f"{settings.API_V1_STR}/servers/{server.id}",
        headers=superuser_token_headers,
        json={"status": "disabled"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["country"] == "DE"
    assert payload["city"] == "Berlin"


async def test_put_server_status_requires_matching_group_key(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    group, group_api_key = await create_server_group(db)
    other_group, _ = await create_server_group(db)
    server = await create_server(db, group_id=group.id)
    _, wrong_api_key = await crud.rotate_server_group_api_key(
        session=db,
        group=other_group,
    )

    response = await client.put(
        f"{settings.API_V1_STR}/servers/status",
        headers={"X-Server-Group-Key": wrong_api_key},
        json={
            "ip": server.ip,
            "port": server.port,
            "observed_at": datetime.now(UTC).isoformat(),
            "hostname": "Plugin Host",
            "map": "kz_plugin",
            "player_count": 9,
            "max_players": 24,
            "players": [_plugin_player()],
        },
    )

    assert group_api_key != wrong_api_key
    assert response.status_code == 403


async def test_put_server_status_updates_live_status_from_plugin(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    group, api_key = await create_server_group(db)
    server = await create_server(db, group_id=group.id)
    observed_at = datetime.now(UTC)
    broadcasted_server_ids: list[str] = []

    async def _fake_broadcast_server_update(server: object) -> None:
        broadcasted_server_ids.append(str(server.id))

    monkeypatch.setattr(
        servers_route,
        "broadcast_server_update",
        _fake_broadcast_server_update,
    )

    response = await client.put(
        f"{settings.API_V1_STR}/servers/status",
        headers={"X-Server-Group-Key": api_key},
        json={
            "ip": server.ip,
            "port": server.port,
            "observed_at": observed_at.isoformat(),
            "hostname": "Plugin Host",
            "map": "kz_plugin",
            "player_count": 9,
            "max_players": 24,
            "players": [_plugin_player()],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["live_status"]["hostname"] == "Plugin Host"
    assert payload["live_status"]["map"] == "kz_plugin"
    assert payload["live_status"]["player_count"] == 9
    assert payload["live_status"]["players"][0]["name"] == "Player One"
    assert payload["live_status"]["players"][0]["status"] == "in_progress"
    assert payload["live_status"]["players"][0]["teleports"] == 3
    assert (
        datetime.fromisoformat(
            payload["live_status"]["state"]["last_plugin_seen_at"].replace(
                "Z", "+00:00"
            )
        )
        == observed_at
    )
    assert broadcasted_server_ids == [str(server.id)]

    refreshed_group = await db.get(ServerGroup, group.id)
    assert refreshed_group is not None
    await db.refresh(refreshed_group)
    assert refreshed_group.status == ServerGroupStatus.VALIDATED
    assert refreshed_group.last_api_key_used_at is not None
    assert refreshed_group.last_api_key_used_at >= observed_at


async def test_put_server_status_accepts_blank_player_mode(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    group, api_key = await create_server_group(db)
    server = await create_server(db, group_id=group.id)
    player = _plugin_player(name="Mode Pending")
    player["mode"] = ""

    response = await client.put(
        f"{settings.API_V1_STR}/servers/status",
        headers={"X-Server-Group-Key": api_key},
        json={
            "ip": server.ip,
            "port": server.port,
            "observed_at": datetime.now(UTC).isoformat(),
            "hostname": "Plugin Host",
            "map": "kz_plugin",
            "player_count": 1,
            "max_players": 16,
            "players": [player],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["live_status"]["players"][0]["name"] == "Mode Pending"
    assert payload["live_status"]["players"][0]["mode"] is None


async def test_put_server_status_auto_creates_missing_server_for_group(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    group, api_key = await create_server_group(db)
    ip = random_server_ip()
    port = random_server_port()
    observed_at = datetime.now(UTC)

    monkeypatch.setattr(
        server_crud,
        "lookup_ip_location",
        _async_location(GeoIPLocation(country_code="DE", city_name="Berlin")),
    )

    response = await client.put(
        f"{settings.API_V1_STR}/servers/status",
        headers={"X-Server-Group-Key": api_key},
        json={
            "ip": ip,
            "port": port,
            "observed_at": observed_at.isoformat(),
            "hostname": "Plugin Bootstrap Host",
            "map": "kz_bootstrap",
            "player_count": 1,
            "max_players": 24,
            "players": [_plugin_player()],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["group_id"] == str(group.id)
    assert payload["ip"] == ip
    assert payload["port"] == port
    assert payload["status"] == "enabled"
    assert payload["country"] == "DE"
    assert payload["city"] == "Berlin"
    assert payload["source"]["type"] == "manual"
    assert payload["source"]["origin"] == "plugin"
    assert payload["source"]["server_group_id"] == str(group.id)
    assert payload["live_status"]["hostname"] == "Plugin Bootstrap Host"
    assert payload["live_status"]["map"] == "kz_bootstrap"

    refreshed_group = await db.get(ServerGroup, group.id)
    assert refreshed_group is not None
    assert refreshed_group.status == ServerGroupStatus.VALIDATED


async def test_put_server_status_claims_unassigned_server_for_group(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    group, api_key = await create_server_group(db)
    server = await create_server(db, group_id=None)
    server.group_id = None
    server.source = {"type": "steam_master"}
    db.add(server)
    await db.commit()

    response = await client.put(
        f"{settings.API_V1_STR}/servers/status",
        headers={"X-Server-Group-Key": api_key},
        json={
            "ip": server.ip,
            "port": server.port,
            "observed_at": datetime.now(UTC).isoformat(),
            "hostname": "Claimed Host",
            "map": "kz_claimed",
            "player_count": 2,
            "max_players": 24,
            "players": [_plugin_player()],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["group_id"] == str(group.id)
    assert payload["source"]["type"] == "manual"
    assert payload["source"]["origin"] == "plugin"
    assert payload["live_status"]["hostname"] == "Claimed Host"
    assert payload["live_status"]["map"] == "kz_claimed"


async def test_put_server_status_reenables_disabled_server_for_matching_group(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    group, api_key = await create_server_group(db)
    server = await create_server(db, group_id=group.id, status=ServerStatus.DISABLED)

    response = await client.put(
        f"{settings.API_V1_STR}/servers/status",
        headers={"X-Server-Group-Key": api_key},
        json={
            "ip": server.ip,
            "port": server.port,
            "observed_at": datetime.now(UTC).isoformat(),
            "hostname": "Reenabled Host",
            "map": "kz_reenabled",
            "player_count": 2,
            "max_players": 24,
            "players": [_plugin_player()],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == str(server.id)
    assert payload["group_id"] == str(group.id)
    assert payload["status"] == "enabled"
    assert payload["source"]["type"] == "manual"
    assert payload["source"]["origin"] == "plugin"
    assert payload["live_status"]["hostname"] == "Reenabled Host"
    assert payload["live_status"]["map"] == "kz_reenabled"


async def test_put_server_status_rejects_disabled_server_owned_by_other_group(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    owning_group, _ = await create_server_group(db)
    other_group, api_key = await create_server_group(db)
    server = await create_server(
        db,
        group_id=owning_group.id,
        status=ServerStatus.DISABLED,
    )

    response = await client.put(
        f"{settings.API_V1_STR}/servers/status",
        headers={"X-Server-Group-Key": api_key},
        json={
            "ip": server.ip,
            "port": server.port,
            "observed_at": datetime.now(UTC).isoformat(),
            "hostname": "Wrong Group Host",
            "map": "kz_wrong_group",
            "player_count": 2,
            "max_players": 24,
            "players": [_plugin_player()],
        },
    )

    assert other_group.id != owning_group.id
    assert response.status_code == 403
    assert response.json()["detail"] == "Server does not belong to this server group"


async def test_put_server_status_accepts_bearer_server_group_key(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    group, api_key = await create_server_group(db)
    server = await create_server(db, group_id=group.id)

    response = await client.put(
        f"{settings.API_V1_STR}/servers/status",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "ip": server.ip,
            "port": server.port,
            "observed_at": datetime.now(UTC).isoformat(),
            "hostname": "Plugin Host",
            "map": "kz_plugin",
            "player_count": 9,
            "max_players": 24,
            "players": [_plugin_player()],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["live_status"]["hostname"] == "Plugin Host"
    assert payload["live_status"]["players"][0]["name"] == "Player One"


async def test_put_server_status_rejects_invalidated_group(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    group, api_key = await create_server_group(db, status=ServerGroupStatus.INVALIDATED)
    server = await create_server(db, group_id=group.id)

    response = await client.put(
        f"{settings.API_V1_STR}/servers/status",
        headers={"X-Server-Group-Key": api_key},
        json={
            "ip": server.ip,
            "port": server.port,
            "observed_at": datetime.now(UTC).isoformat(),
            "hostname": "Plugin Host",
            "map": "kz_plugin",
            "player_count": 9,
            "max_players": 24,
            "players": [_plugin_player()],
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Server group is invalidated"


async def test_read_servers_hides_invalidated_server_groups(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    group, _ = await create_server_group(db, status=ServerGroupStatus.INVALIDATED)
    server = await create_server(db, group_id=group.id, status=ServerStatus.DISABLED)

    response = await client.get(f"{settings.API_V1_STR}/servers")

    assert response.status_code == 200
    payload = response.json()
    assert all(item["id"] != str(server.id) for item in payload["data"])


async def test_offline_mark_preserves_identity_and_zeroes_player_state(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    server = await create_server(
        db,
        hostname="Identity Host",
        map_name="kz_offline",
        player_count=4,
        max_players=20,
    )
    server = await crud.record_plugin_heartbeat(
        session=db,
        server=server,
        payload=ServerStatusPut(
            ip=server.ip,
            port=server.port,
            observed_at=datetime.now(UTC) - timedelta(seconds=10),
            hostname="Identity Host",
            map="kz_offline",
            player_count=4,
            max_players=20,
            players=[_plugin_player()],
        ),
    )
    server = await crud.record_offline_mark(
        session=db,
        server=server,
        observed_at=datetime.now(UTC),
    )

    response = await client.get(
        f"{settings.API_V1_STR}/servers",
        params={"online": False, "limit": 200},
    )

    assert response.status_code == 200
    payload = response.json()
    matching = next(item for item in payload["data"] if item["id"] == str(server.id))
    assert matching["status"] == "enabled"
    assert matching["live_status"]["hostname"] == "Identity Host"
    assert matching["live_status"]["map"] == "kz_offline"
    assert matching["live_status"]["player_count"] == 0
    assert matching["live_status"]["players"] == []
    assert matching["live_status"]["is_online"] is False


async def test_read_servers_returns_map_tier_for_known_map(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    await _create_map(db, id=930210, name="kz_tiered", difficulty=6)
    await create_server(db, hostname="Tier Host", map_name="kz_tiered")

    response = await client.get(
        f"{settings.API_V1_STR}/servers",
        params={"limit": 200},
    )

    assert response.status_code == 200
    payload = response.json()
    matching = next(
        item for item in payload["data"] if item["live_status"]["map"] == "kz_tiered"
    )
    assert matching["map_tier"] == 6
    assert matching["live_status"]["workshop_id"] == "1986459033"


async def test_read_servers_normalizes_prefixed_live_map_for_display_and_tier(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    await _create_map(db, id=930211, name="kz_dakow", difficulty=5)
    await create_server(
        db,
        hostname="Workshop Host",
        map_name="workshop/123456789/kz_dakow",
    )

    response = await client.get(
        f"{settings.API_V1_STR}/servers",
        params={"limit": 200},
    )

    assert response.status_code == 200
    payload = response.json()
    matching = next(
        item for item in payload["data"] if item["live_status"]["map"] == "kz_dakow"
    )
    assert matching["live_status"]["workshop_id"] == "123456789"
    assert matching["map_tier"] == 5


async def test_read_server_returns_null_map_tier_for_unknown_map(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    server = await create_server(
        db, hostname="Unknown Tier", map_name="kz_missing_tier"
    )

    response = await client.get(f"{settings.API_V1_STR}/servers/{server.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["live_status"]["map"] == "kz_missing_tier"
    assert payload["map_tier"] is None


async def test_read_server_normalizes_legacy_player_status_rows(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    server = await create_server(db, hostname="Legacy Player Host")
    assert server.live_status is not None
    server.live_status.players = [
        {
            "name": "Legacy Player",
            "score": 4,
            "status": "paused",
            "duration_seconds": 12.5,
        }
    ]
    db.add(server.live_status)
    await db.commit()

    response = await client.get(f"{settings.API_V1_STR}/servers/{server.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["live_status"]["players"] == [
        {
            "name": "Legacy Player",
            "score": 4,
            "status": None,
            "duration_seconds": 12.5,
            "tag": None,
            "mode": None,
            "is_paused": None,
            "steamid64": None,
            "teleports": None,
            "timer_time": None,
            "stage": None,
            "index": None,
        }
    ]


async def test_server_history_returns_no_new_rows_when_raw_heartbeat_writes_are_disabled(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    server = await create_server(db)
    first_time = datetime.now(UTC).replace(second=0, microsecond=0) + timedelta(
        minutes=1
    )
    second_time = first_time + timedelta(seconds=10)
    third_time = first_time + timedelta(minutes=1)

    server = await crud.record_plugin_heartbeat(
        session=db,
        server=server,
        payload=ServerStatusPut(
            ip=server.ip,
            port=server.port,
            observed_at=first_time,
            hostname="Bucket Host",
            map="kz_history",
            player_count=2,
            max_players=20,
            players=[],
        ),
    )
    server = await crud.record_plugin_heartbeat(
        session=db,
        server=server,
        payload=ServerStatusPut(
            ip=server.ip,
            port=server.port,
            observed_at=second_time,
            hostname="Bucket Host",
            map="kz_history",
            player_count=3,
            max_players=20,
            players=[],
        ),
    )
    await crud.record_plugin_heartbeat(
        session=db,
        server=server,
        payload=ServerStatusPut(
            ip=server.ip,
            port=server.port,
            observed_at=third_time,
            hostname="Bucket Host",
            map="kz_history",
            player_count=5,
            max_players=20,
            players=[],
        ),
    )

    response = await client.get(
        f"{settings.API_V1_STR}/servers/{server.id}/history",
        params={
            "from_at": first_time.isoformat(),
            "to_at": (third_time + timedelta(seconds=1)).isoformat(),
            "bucket_seconds": 60,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 0
    assert payload["data"] == []
