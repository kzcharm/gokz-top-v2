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
    unauthenticated_response = await client.get(
        f"{settings.API_V1_STR}/admin/player-sessions"
    )
    normal_user_response = await client.get(
        f"{settings.API_V1_STR}/admin/player-sessions",
        headers=normal_user_token_headers,
    )

    assert unauthenticated_response.status_code in {401, 403}
    assert normal_user_response.status_code == 403


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
