from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.core.config import settings
from app.crud import player as player_crud
from app.models import Player, PlayerFollow
from tests.utils.utils import get_user_token_headers, random_steamid64


async def _create_player(
    *,
    db: AsyncSession,
    steamid64: int,
    name: str,
    created_at: datetime | None = None,
    custom_id: str | None = None,
) -> Player:
    now = created_at or datetime.now(UTC)
    player = Player(
        steamid64=steamid64,
        name=name,
        custom_id=custom_id,
        created_at=now,
        updated_at=now,
    )
    db.add(player)
    await db.commit()
    await db.refresh(player)
    return player


@pytest.mark.asyncio
async def test_read_players_public_with_offset_and_limit(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    base_time = datetime.now(UTC) + timedelta(days=1)
    await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Offset One",
        created_at=base_time + timedelta(minutes=3),
    )
    await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Offset Two",
        created_at=base_time + timedelta(minutes=2),
    )
    await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Offset Three",
        created_at=base_time + timedelta(minutes=1),
    )

    first_page_response = await client.get(
        f"{settings.API_V1_STR}/players/",
        params={"offset": 0, "limit": 3},
    )
    second_page_response = await client.get(
        f"{settings.API_V1_STR}/players/",
        params={"offset": 1, "limit": 2},
    )

    assert first_page_response.status_code == 200
    assert second_page_response.status_code == 200

    first_payload = first_page_response.json()
    second_payload = second_page_response.json()
    assert first_payload["count"] >= 3
    assert second_payload["count"] == first_payload["count"]
    assert len(first_payload["data"]) == 3
    assert len(second_payload["data"]) == 2
    assert second_payload["data"] == first_payload["data"][1:3]


@pytest.mark.asyncio
async def test_read_players_public_supports_sort_by_last_played_at(
    db: AsyncSession,
) -> None:
    base_time = datetime.now(UTC) + timedelta(days=3)

    first = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Sort First",
        created_at=base_time,
    )
    first.last_played_at = base_time + timedelta(hours=2)
    db.add(first)

    second = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Sort Second",
        created_at=base_time + timedelta(minutes=1),
    )
    second.last_played_at = base_time + timedelta(hours=1)
    db.add(second)
    await db.commit()

    player_ids = [first.steamid64, second.steamid64]
    ascending_players = list(
        (
            await db.exec(
                select(Player)
                .where(col(Player.steamid64).in_(player_ids))
                .order_by(col(Player.last_played_at).asc(), col(Player.steamid64).desc())
            )
        ).all()
    )
    descending_players = list(
        (
            await db.exec(
                select(Player)
                .where(col(Player.steamid64).in_(player_ids))
                .order_by(
                    col(Player.last_played_at).desc(), col(Player.steamid64).desc()
                )
            )
        ).all()
    )

    ascending_ids = [str(item.steamid64) for item in ascending_players]
    descending_ids = [str(item.steamid64) for item in descending_players]

    assert ascending_ids.index(str(second.steamid64)) < ascending_ids.index(
        str(first.steamid64)
    )
    assert descending_ids.index(str(first.steamid64)) < descending_ids.index(
        str(second.steamid64)
    )


@pytest.mark.asyncio
async def test_read_players_batch_preserves_order_with_nullable_entries(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    player_one = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Batch One",
    )
    player_two = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Batch Two",
    )
    missing_steamid64 = str(random_steamid64())

    request_body = {
        "steamid64s": [
            str(player_two.steamid64),
            missing_steamid64,
            str(player_one.steamid64),
            str(player_two.steamid64),
        ]
    }

    response = await client.post(
        f"{settings.API_V1_STR}/players/",
        json=request_body,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 4
    assert payload["data"][0]["steamid64"] == str(player_two.steamid64)
    assert payload["data"][1] is None
    assert payload["data"][2]["steamid64"] == str(player_one.steamid64)
    assert payload["data"][3]["steamid64"] == str(player_two.steamid64)


@pytest.mark.asyncio
async def test_read_player_by_steamid64(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    player = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Steam ID Player",
        custom_id="steam-id-player",
    )

    response = await client.get(f"{settings.API_V1_STR}/players/{player.steamid64}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["steamid64"] == str(player.steamid64)
    assert payload["custom_id"] == "steam-id-player"
    assert payload["profile_views"] == 0


@pytest.mark.asyncio
async def test_read_player_by_custom_id(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    player = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Custom ID Player",
        custom_id="custom-profile_42",
    )

    response = await client.get(f"{settings.API_V1_STR}/players/{player.custom_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["steamid64"] == str(player.steamid64)
    assert payload["custom_id"] == "custom-profile_42"
    assert payload["profile_views"] == 0


@pytest.mark.asyncio
async def test_read_player_includes_profile_views(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    target = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Viewed Target",
    )
    viewer = await crud.get_or_create_user_from_steam(
        session=db,
        steamid64=random_steamid64(),
    )
    await crud.create_player_profile_view(
        session=db,
        viewer_steamid64=viewer.steamid64,
        target_steamid64=target.steamid64,
    )

    response = await client.get(f"{settings.API_V1_STR}/players/{target.steamid64}")

    assert response.status_code == 200
    assert response.json()["profile_views"] == 1


@pytest.mark.asyncio
async def test_read_player_by_identifier_returns_not_found_for_invalid_custom_id(
    client: AsyncClient,
) -> None:
    response = await client.get(f"{settings.API_V1_STR}/players/123456")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_player_requires_authentication(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    player = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="No Auth Update",
    )
    response = await client.put(
        f"{settings.API_V1_STR}/players/{player.steamid64}",
        json={"alias": "blocked", "country": "DE"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_upsert_player_from_steam_requires_authentication(
    client: AsyncClient,
) -> None:
    response = await client.put(
        f"{settings.API_V1_STR}/players/{random_steamid64()}/steam",
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_update_player_authenticated_persists_changes(
    client: AsyncClient,
    db: AsyncSession,
    normal_user_token_headers: dict[str, str],
) -> None:
    player = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Update Target",
    )

    response = await client.put(
        f"{settings.API_V1_STR}/players/{player.steamid64}",
        headers=normal_user_token_headers,
        json={"alias": "Updated Alias", "country": "DE"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["alias"] == "Updated Alias"
    assert payload["country"] == "DE"

    steamid64 = player.steamid64
    db.expire_all()
    refreshed = await db.get(Player, steamid64)
    assert refreshed is not None
    assert refreshed.alias == "Updated Alias"
    assert refreshed.country == "DE"


@pytest.mark.asyncio
async def test_upsert_player_from_steam_authenticated_succeeds(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    normal_user_token_headers: dict[str, str],
) -> None:
    steamid64 = random_steamid64()

    async def _fake_fetch_player_from_steam_api(
        _steamid64: int,
    ) -> dict[str, str | None]:
        return {
            "name": "Steam Synced",
            "custom_id": "steam-synced",
            "avatar_hash": "a" * 40,
            "country": "DE",
            "fetched": True,
        }

    monkeypatch.setattr(
        player_crud,
        "_fetch_player_from_steam_api",
        _fake_fetch_player_from_steam_api,
    )

    response = await client.put(
        f"{settings.API_V1_STR}/players/{steamid64}/steam",
        headers=normal_user_token_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["steamid64"] == str(steamid64)
    assert payload["name"] == "Steam Synced"
    assert payload["custom_id"] == "steam-synced"
    assert payload["country"] == "DE"

    refreshed = await db.get(Player, steamid64)
    assert refreshed is not None
    assert refreshed.name == "Steam Synced"


@pytest.mark.asyncio
async def test_upsert_player_from_steam_normalizes_custom_id_to_lowercase(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    normal_user_token_headers: dict[str, str],
) -> None:
    steamid64 = random_steamid64()

    async def _fake_fetch_player_from_steam_api(
        _steamid64: int,
    ) -> dict[str, str | None]:
        return {
            "name": "Steam Synced",
            "custom_id": "Steam_Synced-42",
            "avatar_hash": "a" * 40,
            "country": "DE",
            "fetched": True,
        }

    monkeypatch.setattr(
        player_crud,
        "_fetch_player_from_steam_api",
        _fake_fetch_player_from_steam_api,
    )

    response = await client.put(
        f"{settings.API_V1_STR}/players/{steamid64}/steam",
        headers=normal_user_token_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["custom_id"] == "steam_synced-42"

    refreshed = await db.get(Player, steamid64)
    assert refreshed is not None
    assert refreshed.custom_id == "steam_synced-42"


@pytest.mark.asyncio
async def test_upsert_player_from_steam_does_not_overwrite_existing_player_when_fetch_fails(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    normal_user_token_headers: dict[str, str],
) -> None:
    steamid64 = random_steamid64()
    db.add(
        Player(
            steamid64=steamid64,
            name="Existing Name",
            custom_id="existing_custom",
            avatar_hash="b" * 40,
            country="US",
        )
    )
    await db.commit()

    async def _fake_fetch_player_from_steam_api(
        _steamid64: int,
    ) -> dict[str, str | None]:
        return {
            "name": str(_steamid64),
            "custom_id": None,
            "avatar_hash": None,
            "country": None,
            "fetched": None,
        }

    monkeypatch.setattr(
        player_crud,
        "_fetch_player_from_steam_api",
        _fake_fetch_player_from_steam_api,
    )

    response = await client.put(
        f"{settings.API_V1_STR}/players/{steamid64}/steam",
        headers=normal_user_token_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "Existing Name"
    assert payload["custom_id"] == "existing_custom"
    assert payload["country"] == "US"

    db.expire_all()
    refreshed = await db.get(Player, steamid64)
    assert refreshed is not None
    assert refreshed.name == "Existing Name"
    assert refreshed.custom_id == "existing_custom"
    assert refreshed.avatar_hash == "b" * 40
    assert refreshed.country == "US"


@pytest.mark.asyncio
async def test_upsert_player_from_steam_does_not_insert_player_when_fetch_fails(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    normal_user_token_headers: dict[str, str],
) -> None:
    steamid64 = random_steamid64()

    async def _fake_fetch_player_from_steam_api(
        _steamid64: int,
    ) -> dict[str, str | bool | None]:
        return {
            "name": str(_steamid64),
            "custom_id": None,
            "avatar_hash": None,
            "country": None,
            "fetched": False,
        }

    monkeypatch.setattr(
        player_crud,
        "_fetch_player_from_steam_api",
        _fake_fetch_player_from_steam_api,
    )

    response = await client.put(
        f"{settings.API_V1_STR}/players/{steamid64}/steam",
        headers=normal_user_token_headers,
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "Steam profile fetch failed"
    assert await db.get(Player, steamid64) is None


@pytest.mark.asyncio
async def test_read_player_follow_summary_is_public(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    target = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Public Summary",
    )
    follower_headers = await get_user_token_headers(client, random_steamid64())

    await client.post(
        f"{settings.API_V1_STR}/players/{target.steamid64}/follow",
        headers=follower_headers,
    )

    response = await client.get(
        f"{settings.API_V1_STR}/players/{target.steamid64}/follow-summary"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["follower_count"] == 1
    assert payload["following_count"] == 0
    assert payload["viewer_is_following"] is None
    assert payload["viewer_is_self"] is False


@pytest.mark.asyncio
async def test_read_player_follow_summary_includes_authenticated_viewer_state(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    target = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Viewer State",
    )
    viewer_steamid64 = random_steamid64()
    viewer_headers = await get_user_token_headers(client, viewer_steamid64)

    await client.post(
        f"{settings.API_V1_STR}/players/{target.steamid64}/follow",
        headers=viewer_headers,
    )

    response = await client.get(
        f"{settings.API_V1_STR}/players/{target.steamid64}/follow-summary",
        headers=viewer_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["follower_count"] == 1
    assert payload["viewer_is_following"] is True
    assert payload["viewer_is_self"] is False


@pytest.mark.asyncio
async def test_follow_and_unfollow_player_require_authentication(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    target = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Auth Target",
    )

    follow_response = await client.post(
        f"{settings.API_V1_STR}/players/{target.steamid64}/follow",
    )
    unfollow_response = await client.delete(
        f"{settings.API_V1_STR}/players/{target.steamid64}/follow",
    )

    assert follow_response.status_code == 401
    assert unfollow_response.status_code == 401


@pytest.mark.asyncio
async def test_follow_player_rejects_self_follow(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    steamid64 = random_steamid64()
    await crud.get_or_create_user_from_steam(session=db, steamid64=steamid64)
    headers = await get_user_token_headers(client, steamid64)

    response = await client.post(
        f"{settings.API_V1_STR}/players/{steamid64}/follow",
        headers=headers,
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "You cannot follow yourself"


@pytest.mark.asyncio
async def test_follow_lists_require_authentication(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    target = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="List Auth Target",
    )

    followers_response = await client.get(
        f"{settings.API_V1_STR}/players/{target.steamid64}/followers"
    )
    following_response = await client.get(
        f"{settings.API_V1_STR}/players/{target.steamid64}/following"
    )

    assert followers_response.status_code == 401
    assert following_response.status_code == 401


@pytest.mark.asyncio
async def test_follow_and_unfollow_player_return_updated_summary(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    target = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Summary Update Target",
    )
    viewer_headers = await get_user_token_headers(client, random_steamid64())

    follow_response = await client.post(
        f"{settings.API_V1_STR}/players/{target.steamid64}/follow",
        headers=viewer_headers,
    )
    unfollow_response = await client.delete(
        f"{settings.API_V1_STR}/players/{target.steamid64}/follow",
        headers=viewer_headers,
    )

    assert follow_response.status_code == 200
    assert follow_response.json()["follower_count"] == 1
    assert follow_response.json()["viewer_is_following"] is True

    assert unfollow_response.status_code == 200
    assert unfollow_response.json()["follower_count"] == 0
    assert unfollow_response.json()["viewer_is_following"] is False


@pytest.mark.asyncio
async def test_follow_lists_return_players_in_newest_first_order(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    viewer_headers = await get_user_token_headers(client, random_steamid64())
    target = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="List Target",
    )
    follower_one = await crud.get_or_create_user_from_steam(
        session=db,
        steamid64=random_steamid64(),
    )
    follower_two = await crud.get_or_create_user_from_steam(
        session=db,
        steamid64=random_steamid64(),
    )
    followed_one = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Followed One",
    )
    followed_two = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Followed Two",
    )
    await crud.get_or_create_user_from_steam(
        session=db,
        steamid64=target.steamid64,
    )
    db.add(
        PlayerFollow(
            follower_steamid64=follower_one.steamid64,
            followed_steamid64=target.steamid64,
            created_at=datetime.now(UTC) - timedelta(minutes=2),
        )
    )
    db.add(
        PlayerFollow(
            follower_steamid64=follower_two.steamid64,
            followed_steamid64=target.steamid64,
            created_at=datetime.now(UTC) - timedelta(minutes=1),
        )
    )
    db.add(
        PlayerFollow(
            follower_steamid64=target.steamid64,
            followed_steamid64=followed_one.steamid64,
            created_at=datetime.now(UTC) - timedelta(minutes=2),
        )
    )
    db.add(
        PlayerFollow(
            follower_steamid64=target.steamid64,
            followed_steamid64=followed_two.steamid64,
            created_at=datetime.now(UTC) - timedelta(minutes=1),
        )
    )
    await db.commit()

    followers_response = await client.get(
        f"{settings.API_V1_STR}/players/{target.steamid64}/followers",
        headers=viewer_headers,
    )
    following_response = await client.get(
        f"{settings.API_V1_STR}/players/{target.steamid64}/following",
        headers=viewer_headers,
    )

    assert followers_response.status_code == 200
    assert followers_response.json()["count"] == 2
    assert [row["steamid64"] for row in followers_response.json()["data"]] == [
        str(follower_two.steamid64),
        str(follower_one.steamid64),
    ]

    assert following_response.status_code == 200
    assert following_response.json()["count"] == 2
    assert [row["steamid64"] for row in following_response.json()["data"]] == [
        str(followed_two.steamid64),
        str(followed_one.steamid64),
    ]


@pytest.mark.asyncio
async def test_follow_routes_return_not_found_for_missing_player(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    missing_identifier = str(random_steamid64())

    summary_response = await client.get(
        f"{settings.API_V1_STR}/players/{missing_identifier}/follow-summary"
    )
    follow_response = await client.post(
        f"{settings.API_V1_STR}/players/{missing_identifier}/follow",
        headers=normal_user_token_headers,
    )
    followers_response = await client.get(
        f"{settings.API_V1_STR}/players/{missing_identifier}/followers",
        headers=normal_user_token_headers,
    )

    assert summary_response.status_code == 404
    assert follow_response.status_code == 404
    assert followers_response.status_code == 404


@pytest.mark.asyncio
async def test_create_player_view_requires_authentication(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    target = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Auth View Target",
    )

    response = await client.post(f"{settings.API_V1_STR}/players/{target.steamid64}/views")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_player_view_records_once_per_utc_day(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Daily View Target",
    )
    viewer_headers = await get_user_token_headers(client, random_steamid64())

    monkeypatch.setattr(
        "app.crud.player_profile_view.get_utc_today",
        lambda *, now=None: datetime(2026, 4, 4, tzinfo=UTC).date(),
    )

    first_response = await client.post(
        f"{settings.API_V1_STR}/players/{target.steamid64}/views",
        headers=viewer_headers,
    )
    second_response = await client.post(
        f"{settings.API_V1_STR}/players/{target.steamid64}/views",
        headers=viewer_headers,
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_response.json()["profile_views"] == 1
    assert second_response.json()["profile_views"] == 1


@pytest.mark.asyncio
async def test_create_player_view_counts_again_after_utc_rollover(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Rollover Target",
    )
    viewer_steamid64 = random_steamid64()
    viewer_headers = await get_user_token_headers(client, viewer_steamid64)

    monkeypatch.setattr(
        "app.crud.player_profile_view.get_utc_today",
        lambda *, now=None: datetime(2026, 4, 4, tzinfo=UTC).date(),
    )
    first_response = await client.post(
        f"{settings.API_V1_STR}/players/{target.steamid64}/views",
        headers=viewer_headers,
    )

    monkeypatch.setattr(
        "app.crud.player_profile_view.get_utc_today",
        lambda *, now=None: datetime(2026, 4, 5, tzinfo=UTC).date(),
    )
    second_response = await client.post(
        f"{settings.API_V1_STR}/players/{target.steamid64}/views",
        headers=viewer_headers,
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_response.json()["profile_views"] == 1
    assert second_response.json()["profile_views"] == 2


@pytest.mark.asyncio
async def test_create_player_view_does_not_count_self_views(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    steamid64 = random_steamid64()
    await crud.get_or_create_user_from_steam(session=db, steamid64=steamid64)
    headers = await get_user_token_headers(client, steamid64)

    response = await client.post(
        f"{settings.API_V1_STR}/players/{steamid64}/views",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["profile_views"] == 0


@pytest.mark.asyncio
async def test_create_player_view_returns_not_found_for_missing_player(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    response = await client.post(
        f"{settings.API_V1_STR}/players/{random_steamid64()}/views",
        headers=normal_user_token_headers,
    )

    assert response.status_code == 404
