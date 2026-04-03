from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.crud import player as player_crud
from app.models import Player
from tests.utils.utils import random_steamid64


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
