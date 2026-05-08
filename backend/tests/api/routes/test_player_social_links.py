import uuid
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.v1 import players as players_routes
from app.core.config import settings
from app.models import Player
from app.services.bilibili_social_link_verification import (
    create_bilibili_pending_confirmation_token,
)
from app.services.twitch_social_link_verification import (
    TwitchAuthenticatedUser,
    create_twitch_pending_confirmation_token,
    create_twitch_verification_state_token,
    decode_twitch_verification_state_token,
)
from tests.utils.user import authentication_token_from_steamid
from tests.utils.utils import get_superuser_token_headers, random_steamid64

pytestmark = pytest.mark.asyncio


async def _create_player(db: AsyncSession, *, steamid64: int, name: str) -> None:
    db.add(Player(steamid64=steamid64, name=name))
    await db.commit()


async def _create_social_link(
    client: AsyncClient,
    *,
    steamid64: int,
    headers: dict[str, str],
    url: str,
) -> dict[str, object]:
    response = await client.post(
        f"{settings.API_V1_STR}/players/{steamid64}/social-links",
        headers=headers,
        json={"url": url},
    )
    assert response.status_code == 200
    return response.json()["data"][0]


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


async def test_player_bilibili_social_link_verify_start_returns_code_and_token(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    steamid64 = random_steamid64()
    await _create_player(db, steamid64=steamid64, name="Bilibili Verify")
    headers = await authentication_token_from_steamid(
        client=client,
        steamid64=steamid64,
        db=db,
    )
    link = await _create_social_link(
        client,
        steamid64=steamid64,
        headers=headers,
        url="https://space.bilibili.com/123456",
    )

    async def _fake_fetch_profile_text(**_: object) -> str:
        return "current profile text"

    monkeypatch.setattr(
        players_routes,
        "fetch_bilibili_profile_text",
        _fake_fetch_profile_text,
    )

    response = await client.post(
        f"{settings.API_V1_STR}/players/{steamid64}/social-links/{link['id']}/verify/bilibili/start",
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["profile_url"] == "https://space.bilibili.com/123456"
    assert str(uuid.UUID(payload["verification_code"])) == payload["verification_code"]
    assert payload["pending_token"]
    assert payload["current_profile_text"] == "current profile text"


async def test_player_bilibili_social_link_verify_start_rejects_invalid_cases(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    owner_steamid64 = random_steamid64()
    other_steamid64 = random_steamid64()
    await _create_player(db, steamid64=owner_steamid64, name="Owner")
    await _create_player(db, steamid64=other_steamid64, name="Other")
    owner_headers = await authentication_token_from_steamid(
        client=client,
        steamid64=owner_steamid64,
        db=db,
    )
    other_headers = await authentication_token_from_steamid(
        client=client,
        steamid64=other_steamid64,
        db=db,
    )
    bilibili_link = await _create_social_link(
        client,
        steamid64=owner_steamid64,
        headers=owner_headers,
        url="https://space.bilibili.com/123456",
    )
    github_link = await _create_social_link(
        client,
        steamid64=owner_steamid64,
        headers=owner_headers,
        url="https://github.com/cinyan10",
    )

    forbidden = await client.post(
        f"{settings.API_V1_STR}/players/{owner_steamid64}/social-links/{bilibili_link['id']}/verify/bilibili/start",
        headers=other_headers,
    )
    assert forbidden.status_code == 403

    non_bilibili = await client.post(
        f"{settings.API_V1_STR}/players/{owner_steamid64}/social-links/{github_link['id']}/verify/bilibili/start",
        headers=owner_headers,
    )
    assert non_bilibili.status_code == 422

    admin_headers = await get_superuser_token_headers(client)
    verified_update = await client.patch(
        f"{settings.API_V1_STR}/admin/player-social-links/{bilibili_link['id']}",
        headers=admin_headers,
        json={"verified": True},
    )
    assert verified_update.status_code == 200
    verified = await client.post(
        f"{settings.API_V1_STR}/players/{owner_steamid64}/social-links/{bilibili_link['id']}/verify/bilibili/start",
        headers=owner_headers,
    )
    assert verified.status_code == 409


async def test_player_bilibili_social_link_verify_start_rejects_profile_fetch_failure(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    steamid64 = random_steamid64()
    await _create_player(db, steamid64=steamid64, name="Bilibili Fetch Failure")
    headers = await authentication_token_from_steamid(
        client=client,
        steamid64=steamid64,
        db=db,
    )
    link = await _create_social_link(
        client,
        steamid64=steamid64,
        headers=headers,
        url="https://space.bilibili.com/123456",
    )

    async def _failing_fetch(**_: object) -> str:
        raise players_routes.BilibiliProfileFetchError(
            "Failed to read the Bilibili profile text. Try again later."
        )

    monkeypatch.setattr(
        players_routes,
        "fetch_bilibili_profile_text",
        _failing_fetch,
    )

    response = await client.post(
        f"{settings.API_V1_STR}/players/{steamid64}/social-links/{link['id']}/verify/bilibili/start",
        headers=headers,
    )
    assert response.status_code == 503


async def test_player_twitch_social_link_verify_start_returns_authorization_url(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    steamid64 = random_steamid64()
    await _create_player(db, steamid64=steamid64, name="Twitch Verify")
    headers = await authentication_token_from_steamid(
        client=client,
        steamid64=steamid64,
        db=db,
    )
    link = await _create_social_link(
        client,
        steamid64=steamid64,
        headers=headers,
        url="https://www.twitch.tv/cinyan10",
    )
    monkeypatch.setattr(settings, "TWITCH_CLIENT_ID", "test-client")
    monkeypatch.setattr(settings, "TWITCH_CLIENT_SECRET", "test-secret")

    response = await client.post(
        f"{settings.API_V1_STR}/players/{steamid64}/social-links/{link['id']}/verify/twitch/start",
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    parsed = urlparse(payload["authorization_url"])
    params = parse_qs(parsed.query)
    assert parsed.netloc == "id.twitch.tv"
    assert parsed.path == "/oauth2/authorize"
    assert params["client_id"] == ["test-client"]
    assert params["response_type"] == ["code"]
    assert (
        params["redirect_uri"][0]
        == f"{settings.BACKEND_PUBLIC_URL.rstrip('/')}{settings.API_V1_STR}/players/social-links/verify/twitch/callback"
    )
    state = decode_twitch_verification_state_token(params["state"][0])
    assert state.steamid64 == steamid64
    assert state.link_id == link["id"]
    assert state.return_path == "/settings?tab=social-links"


async def test_player_bilibili_social_link_confirm_verifies_matching_profile(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    steamid64 = random_steamid64()
    await _create_player(db, steamid64=steamid64, name="Bilibili Confirm")
    headers = await authentication_token_from_steamid(
        client=client,
        steamid64=steamid64,
        db=db,
    )
    link = await _create_social_link(
        client,
        steamid64=steamid64,
        headers=headers,
        url="https://space.bilibili.com/123456",
    )
    pending_token, verification_code, _expires_at = (
        create_bilibili_pending_confirmation_token(
            steamid64=steamid64,
            link_id=str(link["id"]),
            current_account_identifier="123456",
        )
    )

    async def _fake_verify(**_: object) -> None:
        return None

    monkeypatch.setattr(
        players_routes,
        "verify_bilibili_profile_contains_code",
        _fake_verify,
    )

    response = await client.post(
        f"{settings.API_V1_STR}/players/{steamid64}/social-links/{link['id']}/verify/bilibili/confirm",
        headers=headers,
        json={"pending_token": pending_token},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"][0]["verified"] is True
    assert payload["data"][0]["account_identifier"] == "123456"
    assert str(uuid.UUID(verification_code)) == verification_code


async def test_player_bilibili_social_link_confirm_rejects_invalid_token_and_conflict(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_steamid64 = random_steamid64()
    second_steamid64 = random_steamid64()
    await _create_player(db, steamid64=first_steamid64, name="First")
    await _create_player(db, steamid64=second_steamid64, name="Second")
    first_headers = await authentication_token_from_steamid(
        client=client,
        steamid64=first_steamid64,
        db=db,
    )
    first_link = await _create_social_link(
        client,
        steamid64=first_steamid64,
        headers=first_headers,
        url="https://space.bilibili.com/123456",
    )
    admin_headers = await get_superuser_token_headers(client)
    verified_create = await client.post(
        f"{settings.API_V1_STR}/admin/player-social-links",
        headers=admin_headers,
        json={
            "player_steamid64": str(second_steamid64),
            "url": "https://space.bilibili.com/123456",
            "verified": True,
        },
    )
    assert verified_create.status_code == 200

    async def _fake_verify(**_: object) -> None:
        return None

    monkeypatch.setattr(
        players_routes,
        "verify_bilibili_profile_contains_code",
        _fake_verify,
    )

    invalid = await client.post(
        f"{settings.API_V1_STR}/players/{first_steamid64}/social-links/{first_link['id']}/verify/bilibili/confirm",
        headers=first_headers,
        json={"pending_token": "not-a-token"},
    )
    assert invalid.status_code == 400

    wrong_owner_token, _, _ = create_bilibili_pending_confirmation_token(
        steamid64=second_steamid64,
        link_id=str(first_link["id"]),
        current_account_identifier="123456",
    )
    wrong_owner = await client.post(
        f"{settings.API_V1_STR}/players/{first_steamid64}/social-links/{first_link['id']}/verify/bilibili/confirm",
        headers=first_headers,
        json={"pending_token": wrong_owner_token},
    )
    assert wrong_owner.status_code == 400

    conflict_token, _, _ = create_bilibili_pending_confirmation_token(
        steamid64=first_steamid64,
        link_id=str(first_link["id"]),
        current_account_identifier="123456",
    )
    conflict = await client.post(
        f"{settings.API_V1_STR}/players/{first_steamid64}/social-links/{first_link['id']}/verify/bilibili/confirm",
        headers=first_headers,
        json={"pending_token": conflict_token},
    )
    assert conflict.status_code == 409


async def test_player_bilibili_social_link_confirm_rejects_changed_link_and_missing_code(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    steamid64 = random_steamid64()
    await _create_player(db, steamid64=steamid64, name="Bilibili Changed")
    headers = await authentication_token_from_steamid(
        client=client,
        steamid64=steamid64,
        db=db,
    )
    link = await _create_social_link(
        client,
        steamid64=steamid64,
        headers=headers,
        url="https://space.bilibili.com/123456",
    )
    pending_token, _, _ = create_bilibili_pending_confirmation_token(
        steamid64=steamid64,
        link_id=str(link["id"]),
        current_account_identifier="123456",
    )

    update_response = await client.patch(
        f"{settings.API_V1_STR}/players/{steamid64}/social-links/{link['id']}",
        headers=headers,
        json={"url": "https://space.bilibili.com/654321"},
    )
    assert update_response.status_code == 200

    changed = await client.post(
        f"{settings.API_V1_STR}/players/{steamid64}/social-links/{link['id']}/verify/bilibili/confirm",
        headers=headers,
        json={"pending_token": pending_token},
    )
    assert changed.status_code == 409

    delete_response = await client.delete(
        f"{settings.API_V1_STR}/players/{steamid64}/social-links/{link['id']}",
        headers=headers,
    )
    assert delete_response.status_code == 200

    bilibili_create = await client.post(
        f"{settings.API_V1_STR}/players/{steamid64}/social-links",
        headers=headers,
        json={"url": "https://space.bilibili.com/123456"},
    )
    assert bilibili_create.status_code == 200
    recreated_link = bilibili_create.json()["data"][0]
    recreated_token, _, _ = create_bilibili_pending_confirmation_token(
        steamid64=steamid64,
        link_id=recreated_link["id"],
        current_account_identifier="123456",
    )

    async def _missing_code(**_: object) -> None:
        raise players_routes.BilibiliProfileVerificationCodeMissingError(
            "Verification code not found in the public Bilibili profile text."
        )

    monkeypatch.setattr(
        players_routes,
        "verify_bilibili_profile_contains_code",
        _missing_code,
    )

    missing_code = await client.post(
        f"{settings.API_V1_STR}/players/{steamid64}/social-links/{recreated_link['id']}/verify/bilibili/confirm",
        headers=headers,
        json={"pending_token": recreated_token},
    )
    assert missing_code.status_code == 422


async def test_player_bilibili_social_link_confirm_rejects_upstream_fetch_failure(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    steamid64 = random_steamid64()
    await _create_player(db, steamid64=steamid64, name="Bilibili Fetch Error")
    headers = await authentication_token_from_steamid(
        client=client,
        steamid64=steamid64,
        db=db,
    )
    link = await _create_social_link(
        client,
        steamid64=steamid64,
        headers=headers,
        url="https://space.bilibili.com/123456",
    )
    pending_token, _, _ = create_bilibili_pending_confirmation_token(
        steamid64=steamid64,
        link_id=str(link["id"]),
        current_account_identifier="123456",
    )

    async def _fetch_error(**_: object) -> None:
        raise players_routes.BilibiliProfileFetchError(
            "Failed to fetch the Bilibili profile page. Try again later."
        )

    monkeypatch.setattr(
        players_routes,
        "verify_bilibili_profile_contains_code",
        _fetch_error,
    )

    response = await client.post(
        f"{settings.API_V1_STR}/players/{steamid64}/social-links/{link['id']}/verify/bilibili/confirm",
        headers=headers,
        json={"pending_token": pending_token},
    )
    assert response.status_code == 503


async def test_player_twitch_social_link_verify_start_rejects_invalid_cases(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner_steamid64 = random_steamid64()
    other_steamid64 = random_steamid64()
    await _create_player(db, steamid64=owner_steamid64, name="Owner")
    await _create_player(db, steamid64=other_steamid64, name="Other")
    owner_headers = await authentication_token_from_steamid(
        client=client,
        steamid64=owner_steamid64,
        db=db,
    )
    other_headers = await authentication_token_from_steamid(
        client=client,
        steamid64=other_steamid64,
        db=db,
    )
    twitch_link = await _create_social_link(
        client,
        steamid64=owner_steamid64,
        headers=owner_headers,
        url="https://www.twitch.tv/cinyan10",
    )
    github_link = await _create_social_link(
        client,
        steamid64=owner_steamid64,
        headers=owner_headers,
        url="https://github.com/cinyan10",
    )
    monkeypatch.setattr(settings, "TWITCH_CLIENT_ID", "test-client")
    monkeypatch.setattr(settings, "TWITCH_CLIENT_SECRET", "test-secret")

    forbidden = await client.post(
        f"{settings.API_V1_STR}/players/{owner_steamid64}/social-links/{twitch_link['id']}/verify/twitch/start",
        headers=other_headers,
    )
    assert forbidden.status_code == 403

    non_twitch = await client.post(
        f"{settings.API_V1_STR}/players/{owner_steamid64}/social-links/{github_link['id']}/verify/twitch/start",
        headers=owner_headers,
    )
    assert non_twitch.status_code == 422

    admin_headers = await get_superuser_token_headers(client)
    verified_update = await client.patch(
        f"{settings.API_V1_STR}/admin/player-social-links/{twitch_link['id']}",
        headers=admin_headers,
        json={"verified": True},
    )
    assert verified_update.status_code == 200
    verified = await client.post(
        f"{settings.API_V1_STR}/players/{owner_steamid64}/social-links/{twitch_link['id']}/verify/twitch/start",
        headers=owner_headers,
    )
    assert verified.status_code == 409


async def test_player_twitch_social_link_add_start_returns_authorization_url(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    steamid64 = random_steamid64()
    await _create_player(db, steamid64=steamid64, name="Twitch Add")
    headers = await authentication_token_from_steamid(
        client=client,
        steamid64=steamid64,
        db=db,
    )
    monkeypatch.setattr(settings, "TWITCH_CLIENT_ID", "test-client")
    monkeypatch.setattr(settings, "TWITCH_CLIENT_SECRET", "test-secret")

    response = await client.post(
        f"{settings.API_V1_STR}/players/{steamid64}/social-links/add/twitch/start",
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    parsed = urlparse(payload["authorization_url"])
    params = parse_qs(parsed.query)
    state = decode_twitch_verification_state_token(params["state"][0])
    assert state.mode == "add"
    assert state.link_id is None


async def test_player_twitch_social_link_add_callback_creates_verified_link(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    steamid64 = random_steamid64()
    await _create_player(db, steamid64=steamid64, name="Add Callback User")
    headers = await authentication_token_from_steamid(
        client=client,
        steamid64=steamid64,
        db=db,
    )
    state = create_twitch_verification_state_token(
        steamid64=steamid64,
        return_path="/settings?tab=social-links",
        mode="add",
    )

    async def _fake_token(**_: object) -> str:
        return "user-token"

    monkeypatch.setattr(players_routes, "exchange_twitch_code_for_access_token", _fake_token)

    async def _fake_user(**_: object) -> TwitchAuthenticatedUser:
        return TwitchAuthenticatedUser(
            account_identifier="newstreamer",
            display_name="NewStreamer",
        )

    monkeypatch.setattr(players_routes, "fetch_twitch_authenticated_user", _fake_user)

    response = await client.get(
        f"{settings.API_V1_STR}/players/social-links/verify/twitch/callback",
        params={"state": state, "code": "oauth-code"},
        follow_redirects=False,
    )

    assert response.status_code in {302, 307}
    assert response.headers["location"] == (
        f"{settings.FRONTEND_HOST.rstrip('/')}/settings"
        "?tab=social-links&twitchVerification=success"
    )
    links_response = await client.get(
        f"{settings.API_V1_STR}/players/{steamid64}/social-links",
        headers=headers,
    )
    payload = links_response.json()
    assert payload["count"] == 1
    assert payload["data"][0]["platform"] == "twitch"
    assert payload["data"][0]["verified"] is True


async def test_player_twitch_social_link_callback_verifies_matching_account(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    steamid64 = random_steamid64()
    await _create_player(db, steamid64=steamid64, name="Callback User")
    headers = await authentication_token_from_steamid(
        client=client,
        steamid64=steamid64,
        db=db,
    )
    link = await _create_social_link(
        client,
        steamid64=steamid64,
        headers=headers,
        url="https://www.twitch.tv/cinyan10",
    )
    state = create_twitch_verification_state_token(
        steamid64=steamid64,
        link_id=str(link["id"]),
        return_path="/settings?tab=social-links",
        mode="verify",
    )
    async def _fake_token(**_: object) -> str:
        return "user-token"

    monkeypatch.setattr(players_routes, "exchange_twitch_code_for_access_token", _fake_token)

    async def _fake_user(**_: object) -> TwitchAuthenticatedUser:
        return TwitchAuthenticatedUser(
            account_identifier="cinyan10",
            display_name="Cinyan10",
        )

    monkeypatch.setattr(players_routes, "fetch_twitch_authenticated_user", _fake_user)

    response = await client.get(
        f"{settings.API_V1_STR}/players/social-links/verify/twitch/callback",
        params={"state": state, "code": "oauth-code"},
        follow_redirects=False,
    )

    assert response.status_code in {302, 307}
    assert response.headers["location"] == (
        f"{settings.FRONTEND_HOST.rstrip('/')}/settings"
        "?tab=social-links&twitchVerification=success"
    )
    links_response = await client.get(
        f"{settings.API_V1_STR}/players/{steamid64}/social-links"
    )
    assert links_response.json()["data"][0]["verified"] is True


async def test_player_twitch_social_link_callback_redirects_mismatch_without_mutation(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    steamid64 = random_steamid64()
    await _create_player(db, steamid64=steamid64, name="Mismatch User")
    headers = await authentication_token_from_steamid(
        client=client,
        steamid64=steamid64,
        db=db,
    )
    link = await _create_social_link(
        client,
        steamid64=steamid64,
        headers=headers,
        url="https://www.twitch.tv/cinyan10",
    )
    state = create_twitch_verification_state_token(
        steamid64=steamid64,
        link_id=str(link["id"]),
        return_path="/settings?tab=social-links",
        mode="verify",
    )
    async def _fake_token(**_: object) -> str:
        return "user-token"

    monkeypatch.setattr(players_routes, "exchange_twitch_code_for_access_token", _fake_token)

    async def _fake_user(**_: object) -> TwitchAuthenticatedUser:
        return TwitchAuthenticatedUser(
            account_identifier="otherstreamer",
            display_name="OtherStreamer",
        )

    monkeypatch.setattr(players_routes, "fetch_twitch_authenticated_user", _fake_user)

    response = await client.get(
        f"{settings.API_V1_STR}/players/social-links/verify/twitch/callback",
        params={"state": state, "code": "oauth-code"},
        follow_redirects=False,
    )

    assert response.status_code in {302, 307}
    location = response.headers["location"]
    parsed = urlparse(location)
    params = parse_qs(parsed.query)
    assert params["twitchVerification"] == ["mismatch"]
    assert params["currentAccount"] == ["cinyan10"]
    assert params["authenticatedAccount"] == ["otherstreamer"]
    links_response = await client.get(
        f"{settings.API_V1_STR}/players/{steamid64}/social-links"
    )
    payload = links_response.json()
    assert payload["data"][0]["verified"] is False
    assert payload["data"][0]["account_identifier"] == "cinyan10"


async def test_player_twitch_social_link_confirm_replaces_identifier_and_verifies(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    steamid64 = random_steamid64()
    await _create_player(db, steamid64=steamid64, name="Confirm User")
    headers = await authentication_token_from_steamid(
        client=client,
        steamid64=steamid64,
        db=db,
    )
    link = await _create_social_link(
        client,
        steamid64=steamid64,
        headers=headers,
        url="https://www.twitch.tv/oldname",
    )
    pending_token = create_twitch_pending_confirmation_token(
        steamid64=steamid64,
        link_id=str(link["id"]),
        current_account_identifier="oldname",
        authenticated_account_identifier="newname",
        return_path="/settings?tab=social-links",
    )

    response = await client.post(
        f"{settings.API_V1_STR}/players/{steamid64}/social-links/{link['id']}/verify/twitch/confirm",
        headers=headers,
        json={"pending_token": pending_token},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"][0]["account_identifier"] == "newname"
    assert payload["data"][0]["verified"] is True


async def test_player_twitch_social_link_confirm_rejects_invalid_token_and_conflict(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    first_steamid64 = random_steamid64()
    second_steamid64 = random_steamid64()
    await _create_player(db, steamid64=first_steamid64, name="First")
    await _create_player(db, steamid64=second_steamid64, name="Second")
    first_headers = await authentication_token_from_steamid(
        client=client,
        steamid64=first_steamid64,
        db=db,
    )
    first_link = await _create_social_link(
        client,
        steamid64=first_steamid64,
        headers=first_headers,
        url="https://www.twitch.tv/original",
    )
    admin_headers = await get_superuser_token_headers(client)
    verified_create = await client.post(
        f"{settings.API_V1_STR}/admin/player-social-links",
        headers=admin_headers,
        json={
            "player_steamid64": str(second_steamid64),
            "url": "https://www.twitch.tv/takenname",
            "verified": True,
        },
    )
    assert verified_create.status_code == 200

    invalid = await client.post(
        f"{settings.API_V1_STR}/players/{first_steamid64}/social-links/{first_link['id']}/verify/twitch/confirm",
        headers=first_headers,
        json={"pending_token": "not-a-token"},
    )
    assert invalid.status_code == 400

    wrong_owner_token = create_twitch_pending_confirmation_token(
        steamid64=second_steamid64,
        link_id=str(first_link["id"]),
        current_account_identifier="original",
        authenticated_account_identifier="newname",
        return_path="/settings?tab=social-links",
    )
    wrong_owner = await client.post(
        f"{settings.API_V1_STR}/players/{first_steamid64}/social-links/{first_link['id']}/verify/twitch/confirm",
        headers=first_headers,
        json={"pending_token": wrong_owner_token},
    )
    assert wrong_owner.status_code == 400

    conflict_token = create_twitch_pending_confirmation_token(
        steamid64=first_steamid64,
        link_id=str(first_link["id"]),
        current_account_identifier="original",
        authenticated_account_identifier="takenname",
        return_path="/settings?tab=social-links",
    )
    conflict = await client.post(
        f"{settings.API_V1_STR}/players/{first_steamid64}/social-links/{first_link['id']}/verify/twitch/confirm",
        headers=first_headers,
        json={"pending_token": conflict_token},
    )
    assert conflict.status_code == 409
