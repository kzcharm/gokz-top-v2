import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models import (
    Player,
    PlayerProfileField,
    PlayerProfileFieldChange,
    PlayerSession,
    ServerGroupStatus,
    generate_uuid7,
)
from app.services.geoip import GeoIPLocation
from tests.utils.server import create_server_group
from tests.utils.utils import random_steamid64

pytestmark = pytest.mark.asyncio


def _connect_payload(
    *,
    session_id: str,
    steamid64: int,
    connected_at: datetime,
    ip_address: str = "127.0.0.42",
    map_name: str = "kz_beginner",
) -> dict[str, str]:
    return {
        "session_id": session_id,
        "player_steamid64": str(steamid64),
        "connected_at": connected_at.isoformat(),
        "ip_address": ip_address,
        "map_name": map_name,
    }


async def _connect_session(
    *,
    client: AsyncClient,
    api_key: str,
    session_id: str,
    steamid64: int,
    connected_at: datetime,
    ip_address: str = "127.0.0.42",
) -> dict[str, object]:
    response = await client.post(
        f"{settings.API_V1_STR}/player-sessions/connect",
        headers={"X-Server-Group-Key": api_key},
        json=_connect_payload(
            session_id=session_id,
            steamid64=steamid64,
            connected_at=connected_at,
            ip_address=ip_address,
        ),
    )
    assert response.status_code == 200
    return response.json()


async def test_connect_creates_player_session_and_placeholder_player(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    group, api_key = await create_server_group(db)
    steamid64 = random_steamid64()
    connected_at = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)
    session_id = str(generate_uuid7(timestamp=connected_at))

    payload = await _connect_session(
        client=client,
        api_key=api_key,
        session_id=session_id,
        steamid64=steamid64,
        connected_at=connected_at,
    )

    assert payload["id"] == session_id
    assert payload["player_steamid64"] == str(steamid64)
    assert payload["server_group_id"] == str(group.id)
    assert payload["last_heartbeat_at"] == connected_at.isoformat().replace(
        "+00:00", "Z"
    )
    assert payload["ip_address"] == "127.0.0.42"
    assert payload["map_name"] == "kz_beginner"
    assert payload["duration_seconds"] is None

    player = await db.get(Player, steamid64)
    assert player is not None
    assert player.name == str(steamid64)


async def test_connect_accepts_bearer_server_group_key(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    group, api_key = await create_server_group(db)
    steamid64 = random_steamid64()
    connected_at = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)
    session_id = str(generate_uuid7(timestamp=connected_at))

    response = await client.post(
        f"{settings.API_V1_STR}/player-sessions/connect",
        headers={"Authorization": f"Bearer {api_key}"},
        json=_connect_payload(
            session_id=session_id,
            steamid64=steamid64,
            connected_at=connected_at,
        ),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == session_id
    assert payload["server_group_id"] == str(group.id)


async def test_connect_sets_placeholder_player_country_from_geoip(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.crud.player_session.lookup_geoip_city",
        lambda ip: GeoIPLocation(
            country_code="US",
            region_name="Illinois",
            city_name="Chicago",
        ),
    )
    _, api_key = await create_server_group(db)
    steamid64 = random_steamid64()
    connected_at = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)

    payload = await _connect_session(
        client=client,
        api_key=api_key,
        session_id=str(generate_uuid7(timestamp=connected_at)),
        steamid64=steamid64,
        connected_at=connected_at,
        ip_address="8.8.8.8",
    )

    player = await db.get(Player, steamid64)
    player_session = await db.get(PlayerSession, uuid.UUID(str(payload["id"])))
    assert player is not None
    assert player.country == "US"
    assert player_session is not None
    assert player_session.geo_country == "US"
    assert player_session.geo_region == "Illinois"
    assert player_session.geo_city == "Chicago"


async def test_connect_updates_unlocked_player_country_from_geoip(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.crud.player_session.lookup_geoip_city",
        lambda ip: GeoIPLocation(country_code="US", city_name="Chicago"),
    )
    group, api_key = await create_server_group(db)
    steamid64 = random_steamid64()
    player = Player(steamid64=steamid64, name="Runner", country="CA")
    db.add(player)
    await db.commit()
    connected_at = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)

    await _connect_session(
        client=client,
        api_key=api_key,
        session_id=str(generate_uuid7(timestamp=connected_at)),
        steamid64=steamid64,
        connected_at=connected_at,
    )

    await db.refresh(player)
    assert player.country == "US"


async def test_connect_does_not_update_locked_player_country_from_geoip(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.crud.player_session.lookup_geoip_city",
        lambda ip: GeoIPLocation(country_code="US", city_name="Chicago"),
    )
    group, api_key = await create_server_group(db)
    steamid64 = random_steamid64()
    player = Player(
        steamid64=steamid64,
        name="Runner",
        country="CA",
    )
    db.add(player)
    db.add(
        PlayerProfileFieldChange(
            player_steamid64=steamid64,
            field=PlayerProfileField.COUNTRY,
            changed_at=datetime.now(UTC),
        )
    )
    await db.commit()
    connected_at = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)

    await _connect_session(
        client=client,
        api_key=api_key,
        session_id=str(generate_uuid7(timestamp=connected_at)),
        steamid64=steamid64,
        connected_at=connected_at,
    )

    await db.refresh(player)
    assert player.country == "CA"


async def test_connect_duplicate_is_idempotent_for_same_player_and_group(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    _, api_key = await create_server_group(db)
    steamid64 = random_steamid64()
    connected_at = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)
    session_id = str(generate_uuid7(timestamp=connected_at))

    first = await _connect_session(
        client=client,
        api_key=api_key,
        session_id=session_id,
        steamid64=steamid64,
        connected_at=connected_at,
    )
    second = await _connect_session(
        client=client,
        api_key=api_key,
        session_id=session_id,
        steamid64=steamid64,
        connected_at=connected_at + timedelta(seconds=10),
    )

    assert second == first


async def test_connect_duplicate_rejects_different_player(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    _, api_key = await create_server_group(db)
    connected_at = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)
    session_id = str(generate_uuid7(timestamp=connected_at))
    await _connect_session(
        client=client,
        api_key=api_key,
        session_id=session_id,
        steamid64=random_steamid64(),
        connected_at=connected_at,
    )

    response = await client.post(
        f"{settings.API_V1_STR}/player-sessions/connect",
        headers={"X-Server-Group-Key": api_key},
        json=_connect_payload(
            session_id=session_id,
            steamid64=random_steamid64(),
            connected_at=connected_at,
        ),
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Player session already exists"


async def test_connect_requires_valid_server_group_key(
    client: AsyncClient,
) -> None:
    connected_at = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)
    payload = _connect_payload(
        session_id=str(generate_uuid7(timestamp=connected_at)),
        steamid64=random_steamid64(),
        connected_at=connected_at,
    )

    missing_response = await client.post(
        f"{settings.API_V1_STR}/player-sessions/connect",
        json=payload,
    )
    invalid_response = await client.post(
        f"{settings.API_V1_STR}/player-sessions/connect",
        headers={"X-Server-Group-Key": "not-a-key"},
        json=payload,
    )

    assert missing_response.status_code == 401
    assert invalid_response.status_code == 401


async def test_connect_rejects_invalidated_group(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    _, api_key = await create_server_group(db, status=ServerGroupStatus.INVALIDATED)
    connected_at = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)

    response = await client.post(
        f"{settings.API_V1_STR}/player-sessions/connect",
        headers={"X-Server-Group-Key": api_key},
        json=_connect_payload(
            session_id=str(generate_uuid7(timestamp=connected_at)),
            steamid64=random_steamid64(),
            connected_at=connected_at,
        ),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Server group is invalidated"


async def test_connect_rejects_invalid_uuid_version_and_ipv6(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    _, api_key = await create_server_group(db)
    connected_at = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)

    invalid_uuid_response = await client.post(
        f"{settings.API_V1_STR}/player-sessions/connect",
        headers={"X-Server-Group-Key": api_key},
        json=_connect_payload(
            session_id="0f7a8b4e-32c4-4bbb-a62d-a5af35f15db8",
            steamid64=random_steamid64(),
            connected_at=connected_at,
        ),
    )
    ipv6_response = await client.post(
        f"{settings.API_V1_STR}/player-sessions/connect",
        headers={"X-Server-Group-Key": api_key},
        json=_connect_payload(
            session_id=str(generate_uuid7(timestamp=connected_at)),
            steamid64=random_steamid64(),
            connected_at=connected_at,
            ip_address="::1",
        ),
    )

    assert invalid_uuid_response.status_code == 422
    assert ipv6_response.status_code == 422


async def test_heartbeat_updates_open_session_forward_only(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    _, api_key = await create_server_group(db)
    steamid64 = random_steamid64()
    connected_at = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)
    session_id = str(generate_uuid7(timestamp=connected_at))
    await _connect_session(
        client=client,
        api_key=api_key,
        session_id=session_id,
        steamid64=steamid64,
        connected_at=connected_at,
    )

    heartbeat_at = connected_at + timedelta(seconds=15)
    response = await client.post(
        f"{settings.API_V1_STR}/player-sessions/heartbeat",
        headers={"X-Server-Group-Key": api_key},
        json={"session_id": session_id, "heartbeat_at": heartbeat_at.isoformat()},
    )
    older_response = await client.post(
        f"{settings.API_V1_STR}/player-sessions/heartbeat",
        headers={"X-Server-Group-Key": api_key},
        json={
            "session_id": session_id,
            "heartbeat_at": (connected_at + timedelta(seconds=5)).isoformat(),
        },
    )

    assert response.status_code == 200
    assert response.json()["last_heartbeat_at"] == heartbeat_at.isoformat().replace(
        "+00:00", "Z"
    )
    assert older_response.status_code == 200
    assert older_response.json()["last_heartbeat_at"] == heartbeat_at.isoformat().replace(
        "+00:00", "Z"
    )


async def test_heartbeat_rejects_timestamp_before_connect(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    _, api_key = await create_server_group(db)
    connected_at = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)
    session_id = str(generate_uuid7(timestamp=connected_at))
    await _connect_session(
        client=client,
        api_key=api_key,
        session_id=session_id,
        steamid64=random_steamid64(),
        connected_at=connected_at,
    )

    response = await client.post(
        f"{settings.API_V1_STR}/player-sessions/heartbeat",
        headers={"X-Server-Group-Key": api_key},
        json={
            "session_id": session_id,
            "heartbeat_at": (connected_at - timedelta(seconds=1)).isoformat(),
        },
    )

    assert response.status_code == 422


async def test_disconnect_closes_session_and_returns_generated_duration(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    _, api_key = await create_server_group(db)
    connected_at = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)
    disconnected_at = connected_at + timedelta(seconds=75)
    session_id = str(generate_uuid7(timestamp=connected_at))
    await _connect_session(
        client=client,
        api_key=api_key,
        session_id=session_id,
        steamid64=random_steamid64(),
        connected_at=connected_at,
    )

    response = await client.post(
        f"{settings.API_V1_STR}/player-sessions/disconnect",
        headers={"X-Server-Group-Key": api_key},
        json={"session_id": session_id, "disconnect_at": disconnected_at.isoformat()},
    )
    retry_response = await client.post(
        f"{settings.API_V1_STR}/player-sessions/disconnect",
        headers={"X-Server-Group-Key": api_key},
        json={
            "session_id": session_id,
            "disconnect_at": (disconnected_at + timedelta(seconds=15)).isoformat(),
        },
    )

    assert response.status_code == 200
    assert response.json()["disconnect_at"] == disconnected_at.isoformat().replace(
        "+00:00", "Z"
    )
    assert response.json()["duration_seconds"] == 75
    assert retry_response.status_code == 200
    assert retry_response.json()["disconnect_at"] == response.json()["disconnect_at"]
    assert retry_response.json()["duration_seconds"] == 75
