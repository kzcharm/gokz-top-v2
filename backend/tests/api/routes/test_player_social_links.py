import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models import Player
from tests.utils.user import authentication_token_from_steamid
from tests.utils.utils import get_superuser_token_headers, random_steamid64

pytestmark = pytest.mark.asyncio


async def _create_player(db: AsyncSession, *, steamid64: int, name: str) -> None:
    db.add(Player(steamid64=steamid64, name=name))
    await db.commit()


async def test_player_social_links_parse_supported_platforms_and_sort_alpha(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    steamid64 = random_steamid64()
    await _create_player(db, steamid64=steamid64, name="Social Player")
    headers = await authentication_token_from_steamid(
        client=client,
        steamid64=steamid64,
        db=db,
    )

    for url in [
        "https://x.com/Cinyan10",
        "https://space.bilibili.com/123456",
        "https://www.youtube.com/@Cinyan10",
        "https://github.com/Cinyan10",
        "https://www.twitch.tv/Cinyan10",
    ]:
        response = await client.post(
            f"{settings.API_V1_STR}/players/{steamid64}/social-links",
            headers=headers,
            json={"url": url},
        )
        assert response.status_code == 200

    response = await client.get(
        f"{settings.API_V1_STR}/players/{steamid64}/social-links",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 5
    assert [link["platform"] for link in payload["data"]] == [
        "bilibili",
        "github",
        "twitch",
        "x",
        "youtube",
    ]
    assert payload["data"][0]["account_identifier"] == "123456"
    assert payload["data"][0]["url"] == "https://space.bilibili.com/123456"
    assert payload["data"][0]["verified"] is False
    assert payload["data"][4]["account_identifier"] == "@cinyan10"
    assert payload["data"][4]["url"] == "https://www.youtube.com/@cinyan10"


async def test_player_social_links_reject_non_profile_url(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    steamid64 = random_steamid64()
    await _create_player(db, steamid64=steamid64, name="Social Player")
    headers = await authentication_token_from_steamid(
        client=client,
        steamid64=steamid64,
        db=db,
    )

    response = await client.post(
        f"{settings.API_V1_STR}/players/{steamid64}/social-links",
        headers=headers,
        json={"url": "https://github.com/KZGlobalTeam/gokz"},
    )

    assert response.status_code == 422


async def test_player_social_links_forbid_mutating_another_player(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    owner_steamid64 = random_steamid64()
    other_steamid64 = random_steamid64()
    await _create_player(db, steamid64=owner_steamid64, name="Owner")
    await _create_player(db, steamid64=other_steamid64, name="Other")
    other_headers = await authentication_token_from_steamid(
        client=client,
        steamid64=other_steamid64,
        db=db,
    )

    response = await client.post(
        f"{settings.API_V1_STR}/players/{owner_steamid64}/social-links",
        headers=other_headers,
        json={"url": "https://x.com/cinyan10"},
    )

    assert response.status_code == 403


async def test_player_social_links_one_link_per_platform(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    steamid64 = random_steamid64()
    await _create_player(db, steamid64=steamid64, name="Social Player")
    headers = await authentication_token_from_steamid(
        client=client,
        steamid64=steamid64,
        db=db,
    )

    first = await client.post(
        f"{settings.API_V1_STR}/players/{steamid64}/social-links",
        headers=headers,
        json={"url": "https://x.com/cinyan10"},
    )
    second = await client.post(
        f"{settings.API_V1_STR}/players/{steamid64}/social-links",
        headers=headers,
        json={"url": "https://twitter.com/other_name"},
    )

    assert first.status_code == 200
    assert second.status_code == 409


async def test_player_social_links_owner_can_update_and_delete(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    steamid64 = random_steamid64()
    await _create_player(db, steamid64=steamid64, name="Social Player")
    headers = await authentication_token_from_steamid(
        client=client,
        steamid64=steamid64,
        db=db,
    )

    create_response = await client.post(
        f"{settings.API_V1_STR}/players/{steamid64}/social-links",
        headers=headers,
        json={"url": "https://x.com/cinyan10"},
    )
    link_id = create_response.json()["data"][0]["id"]

    update_response = await client.patch(
        f"{settings.API_V1_STR}/players/{steamid64}/social-links/{link_id}",
        headers=headers,
        json={"url": "https://github.com/cinyan10"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["data"][0]["platform"] == "github"
    assert update_response.json()["data"][0]["verified"] is False

    delete_response = await client.delete(
        f"{settings.API_V1_STR}/players/{steamid64}/social-links/{link_id}",
        headers=headers,
    )
    assert delete_response.status_code == 200
    assert delete_response.json() == {"data": [], "count": 0}


async def test_admin_player_social_links_manage_and_prevent_duplicate_verified_account(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    first_steamid64 = random_steamid64()
    second_steamid64 = random_steamid64()
    await _create_player(db, steamid64=first_steamid64, name="First")
    await _create_player(db, steamid64=second_steamid64, name="Second")
    headers = await get_superuser_token_headers(client)

    create_response = await client.post(
        f"{settings.API_V1_STR}/admin/player-social-links",
        headers=headers,
        json={
            "player_steamid64": str(first_steamid64),
            "url": "https://github.com/cinyan10",
            "verified": True,
        },
    )
    assert create_response.status_code == 200
    payload = create_response.json()
    assert payload["verified"] is True
    assert payload["player"]["steamid64"] == str(first_steamid64)

    duplicate_response = await client.post(
        f"{settings.API_V1_STR}/admin/player-social-links",
        headers=headers,
        json={
            "player_steamid64": str(second_steamid64),
            "url": "https://github.com/cinyan10",
            "verified": True,
        },
    )
    assert duplicate_response.status_code == 409

    list_response = await client.get(
        f"{settings.API_V1_STR}/admin/player-social-links",
        headers=headers,
        params={"platform": "github", "verified": True},
    )
    assert list_response.status_code == 200
    assert list_response.json()["count"] == 1

    update_response = await client.patch(
        f"{settings.API_V1_STR}/admin/player-social-links/{payload['id']}",
        headers=headers,
        json={"verified": False},
    )
    assert update_response.status_code == 200
    assert update_response.json()["verified"] is False

    delete_response = await client.delete(
        f"{settings.API_V1_STR}/admin/player-social-links/{payload['id']}",
        headers=headers,
    )
    assert delete_response.status_code == 200
    assert delete_response.json()["message"] == "Social link deleted successfully"


async def test_player_social_link_verified_partial_unique_allows_unverified_duplicates(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    first_steamid64 = random_steamid64()
    second_steamid64 = random_steamid64()
    await _create_player(db, steamid64=first_steamid64, name="First")
    await _create_player(db, steamid64=second_steamid64, name="Second")
    headers = await get_superuser_token_headers(client)

    for steamid64 in [first_steamid64, second_steamid64]:
        response = await client.post(
            f"{settings.API_V1_STR}/admin/player-social-links",
            headers=headers,
            json={
                "player_steamid64": str(steamid64),
                "url": "https://twitch.tv/cinyan10",
                "verified": False,
            },
        )
        assert response.status_code == 200

    count_row = (
        await db.exec(
            text(
                """
                SELECT count(*)
                FROM player_social_link
                WHERE platform = 'TWITCH'
                  AND account_identifier = 'cinyan10'
                """
            )
        )
    ).one()
    assert count_row[0] == 2
