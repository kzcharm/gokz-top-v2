from datetime import date

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models import Player
from tests.utils.user import authentication_token_from_steamid
from tests.utils.utils import get_superuser_token_headers, random_steamid64

pytestmark = pytest.mark.asyncio


async def _create_player(
    *, db: AsyncSession, steamid64: int, name: str = "Tournament Player"
) -> None:
    db.add(Player(steamid64=steamid64, name=name))
    await db.commit()


async def test_superuser_manages_tournament_achievements_and_profiles_show_them(
    client: AsyncClient, db: AsyncSession
) -> None:
    steamid64 = random_steamid64()
    await _create_player(db=db, steamid64=steamid64)
    headers = await get_superuser_token_headers(client)

    create_tournament = await client.post(
        f"{settings.API_V1_STR}/admin/tournaments",
        headers=headers,
        json={
            "name": "2026 AXE Major",
            "starts_on": "2026-08-01",
            "ends_on": "2026-08-03",
            "official_url": "https://axekz.com/tournament/axe-major",
            "level": "S",
        },
    )
    assert create_tournament.status_code == 200
    tournament = create_tournament.json()
    assert tournament["level"] == "S"

    create_achievement = await client.post(
        f"{settings.API_V1_STR}/admin/tournaments/achievements",
        headers=headers,
        json={
            "tournament_id": tournament["id"],
            "player_steamid64": str(steamid64),
            "placement": 1,
        },
    )
    assert create_achievement.status_code == 200
    achievement = create_achievement.json()
    assert achievement["player"]["steamid64"] == str(steamid64)

    public_response = await client.get(
        f"{settings.API_V1_STR}/players/{steamid64}/tournament-achievements"
    )
    assert public_response.status_code == 200
    payload = public_response.json()
    assert payload["count"] == 1
    assert payload["data"][0]["placement"] == 1
    assert payload["data"][0]["tournament"]["name"] == "2026 AXE Major"

    update_achievement = await client.patch(
        f"{settings.API_V1_STR}/admin/tournaments/achievements/{achievement['id']}",
        headers=headers,
        json={"placement": 4},
    )
    assert update_achievement.status_code == 200
    assert update_achievement.json()["placement"] == 4

    delete_achievement = await client.delete(
        f"{settings.API_V1_STR}/admin/tournaments/achievements/{achievement['id']}",
        headers=headers,
    )
    assert delete_achievement.status_code == 200


async def test_tournament_admin_routes_require_superuser(
    client: AsyncClient, db: AsyncSession
) -> None:
    steamid64 = random_steamid64()
    await _create_player(db=db, steamid64=steamid64)
    headers = await authentication_token_from_steamid(
        client=client, db=db, steamid64=steamid64
    )

    response = await client.post(
        f"{settings.API_V1_STR}/admin/tournaments",
        headers=headers,
        json={
            "name": "Unauthorized",
            "starts_on": date(2026, 8, 1).isoformat(),
            "ends_on": date(2026, 8, 1).isoformat(),
            "level": "C",
        },
    )
    assert response.status_code == 403


async def test_tournament_achievement_rejects_duplicate_and_invalid_placement(
    client: AsyncClient, db: AsyncSession
) -> None:
    steamid64 = random_steamid64()
    await _create_player(db=db, steamid64=steamid64)
    headers = await get_superuser_token_headers(client)
    invalid_dates = await client.post(
        f"{settings.API_V1_STR}/admin/tournaments",
        headers=headers,
        json={
            "name": "Invalid Dates",
            "starts_on": "2026-01-02",
            "ends_on": "2026-01-01",
            "level": "C",
        },
    )
    assert invalid_dates.status_code == 422
    tournament_response = await client.post(
        f"{settings.API_V1_STR}/admin/tournaments",
        headers=headers,
        json={
            "name": "AXE Minor",
            "starts_on": "2026-01-01",
            "ends_on": "2026-01-02",
            "level": "B",
        },
    )
    tournament_id = tournament_response.json()["id"]
    body = {
        "tournament_id": tournament_id,
        "player_steamid64": str(steamid64),
        "placement": 3,
    }
    assert (
        await client.post(
            f"{settings.API_V1_STR}/admin/tournaments/achievements",
            headers=headers,
            json=body,
        )
    ).status_code == 200
    assert (
        await client.post(
            f"{settings.API_V1_STR}/admin/tournaments/achievements",
            headers=headers,
            json=body,
        )
    ).status_code == 409

    body["placement"] = 5
    assert (
        await client.post(
            f"{settings.API_V1_STR}/admin/tournaments/achievements",
            headers=headers,
            json=body,
        )
    ).status_code == 422
