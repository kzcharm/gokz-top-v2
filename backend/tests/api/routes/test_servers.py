from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.api.v1 import servers as servers_route
from app.core.config import settings
from app.crud import server as server_crud
from app.models import (
    Map,
    ServerGroup,
    ServerGroupStatus,
    ServerHeartbeatRaw,
    ServerStatus,
    ServerStatusPut,
)
from app.services.geoip import GeoIPLocation
from app.services.server_status import (
    A2SInfoResult,
    ServerDiscoveryCycleResult,
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
        "lookup_geoip_city",
        lambda ip: GeoIPLocation(country_code="US", city_name="Chicago"),
    )

    response = await client.post(
        f"{settings.API_V1_STR}/servers/",
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
        "lookup_geoip_city",
        lambda ip: GeoIPLocation(country_code="US", city_name="Chicago"),
    )

    response = await client.post(
        f"{settings.API_V1_STR}/servers/",
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


async def test_read_servers_returns_derived_region_and_filters_by_region(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    eu_server = await create_server(db, country="DE", city="Berlin")
    await create_server(db, country="US", city="Chicago")

    response = await client.get(
        f"{settings.API_V1_STR}/servers/",
        params={"region": "EU", "limit": 200},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["data"][0]["id"] == str(eu_server.id)
    assert payload["data"][0]["region"] == "EU"


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
        f"{settings.API_V1_STR}/servers/",
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
        f"{settings.API_V1_STR}/servers/",
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
        f"{settings.API_V1_STR}/servers/discovery",
        headers=normal_user_token_headers,
    )

    assert response.status_code == 403


async def test_trigger_server_discovery_returns_summary(
    client: AsyncClient,
    superuser_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started_at = datetime.now(UTC)
    completed_at = started_at + timedelta(seconds=3)

    async def _fake_run_server_discovery_cycle() -> ServerDiscoveryCycleResult:
        return ServerDiscoveryCycleResult(
            started_at=started_at,
            completed_at=completed_at,
            regions_scanned=8,
            candidate_count=42,
            upserted_count=5,
        )

    monkeypatch.setattr(
        servers_route,
        "run_server_discovery_cycle",
        _fake_run_server_discovery_cycle,
    )

    response = await client.post(
        f"{settings.API_V1_STR}/servers/discovery",
        headers=superuser_token_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["regions_scanned"] == 8
    assert payload["candidate_count"] == 42
    assert payload["upserted_count"] == 5


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
        f"{settings.API_V1_STR}/servers/",
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
        f"{settings.API_V1_STR}/servers/",
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
        "lookup_geoip_city",
        lambda ip: GeoIPLocation(country_code="US", city_name="Chicago"),
    )

    response = await client.post(
        f"{settings.API_V1_STR}/servers/",
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
        "lookup_geoip_city",
        lambda ip: GeoIPLocation(country_code="US", city_name="Chicago"),
    )

    response = await client.post(
        f"{settings.API_V1_STR}/servers/",
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
        f"{settings.API_V1_STR}/servers/",
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
        "lookup_geoip_city",
        lambda ip: GeoIPLocation(country_code="US", city_name="Chicago"),
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


async def test_update_server_preserves_existing_location_values(
    client: AsyncClient,
    db: AsyncSession,
    superuser_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = await create_server(db, country="DE", city="Berlin")
    monkeypatch.setattr(
        server_crud,
        "lookup_geoip_city",
        lambda ip: GeoIPLocation(country_code="US", city_name="Chicago"),
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
            "players": [{"steamid64": "76561198000000001", "name": "Player One"}],
        },
    )

    assert group_api_key != wrong_api_key
    assert response.status_code == 403


async def test_put_server_status_updates_live_status_from_plugin(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    group, api_key = await create_server_group(db)
    server = await create_server(db, group_id=group.id)
    observed_at = datetime.now(UTC)

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
            "players": [{"steamid64": "76561198000000001", "name": "Player One"}],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["live_status"]["hostname"] == "Plugin Host"
    assert payload["live_status"]["map"] == "kz_plugin"
    assert payload["live_status"]["player_count"] == 9
    assert payload["live_status"]["players"][0]["name"] == "Player One"
    assert (
        datetime.fromisoformat(
            payload["live_status"]["last_plugin_seen_at"].replace("Z", "+00:00")
        )
        == observed_at
    )

    refreshed_group = await db.get(ServerGroup, group.id)
    assert refreshed_group is not None
    assert refreshed_group.status == ServerGroupStatus.VALIDATED


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
            "players": [{"steamid64": "76561198000000001", "name": "Player One"}],
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

    response = await client.get(f"{settings.API_V1_STR}/servers/")

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
            players=[{"steamid64": "76561198000000001", "name": "Player One"}],
        ),
    )
    server = await crud.record_offline_mark(
        session=db,
        server=server,
        observed_at=datetime.now(UTC),
    )

    response = await client.get(
        f"{settings.API_V1_STR}/servers/",
        params={"online": False, "limit": 200},
    )

    assert response.status_code == 200
    payload = response.json()
    matching = next(item for item in payload["data"] if item["id"] == str(server.id))
    assert matching["status"] == "invalid"
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
        f"{settings.API_V1_STR}/servers/",
        params={"limit": 200},
    )

    assert response.status_code == 200
    payload = response.json()
    matching = next(
        item for item in payload["data"] if item["live_status"]["map"] == "kz_tiered"
    )
    assert matching["map_tier"] == 6


async def test_read_server_returns_null_map_tier_for_unknown_map(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    server = await create_server(db, hostname="Unknown Tier", map_name="kz_missing_tier")

    response = await client.get(f"{settings.API_V1_STR}/servers/{server.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["live_status"]["map"] == "kz_missing_tier"
    assert payload["map_tier"] is None


async def test_server_history_returns_bucketed_rows(
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
    assert payload["count"] == 2
    assert payload["data"][0]["heartbeat_count"] == 2
    assert payload["data"][1]["heartbeat_count"] == 1

    rows = list(
        (
            await db.exec(
                select(ServerHeartbeatRaw).where(
                    ServerHeartbeatRaw.server_id == server.id
                )
            )
        ).all()
    )
    assert len(rows) >= 4
