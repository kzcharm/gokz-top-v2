from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.api.v1 import me_player_actions as me_player_actions_api
from app.api.v1 import players as players_api
from app.core.config import settings
from app.crud import player as player_crud
from app.models import (
    Ban,
    BanType,
    LeaderboardPlayer,
    ModeScope,
    Player,
    PlayerFollow,
    PlayerProfileField,
    PlayerProfileHistory,
    User,
)
from app.services import globalapi_ban_sync, player_steam_profile
from tests.utils.user import authentication_token_from_steamid
from tests.utils.utils import (
    get_superuser_token_headers,
    get_user_token_headers,
    random_steamid64,
)


async def _create_player(
    *,
    db: AsyncSession,
    steamid64: int,
    name: str,
    created_at: datetime | None = None,
    custom_id: str | None = None,
    avatar_hash: str | None = None,
    steam_profile_synced_at: datetime | None = None,
) -> Player:
    now = created_at or datetime.now(UTC)
    player = Player(
        steamid64=steamid64,
        name=name,
        custom_id=custom_id,
        avatar_hash=avatar_hash,
        steam_profile_synced_at=steam_profile_synced_at,
        created_at=now,
        updated_at=now,
    )
    db.add(player)
    await db.commit()
    await db.refresh(player)
    return player


async def _create_profile_field_change(
    *,
    db: AsyncSession,
    steamid64: int,
    field: PlayerProfileField,
    changed_at: datetime,
) -> None:
    await crud.upsert_player_profile_field_change(
        session=db,
        player_steamid64=steamid64,
        field=field,
        changed_at=changed_at,
    )
    await db.commit()


async def _get_profile_history_rows(
    *,
    db: AsyncSession,
    steamid64: int,
) -> list[PlayerProfileHistory]:
    statement = (
        select(PlayerProfileHistory)
        .where(col(PlayerProfileHistory.player_steamid64) == steamid64)
        .order_by(
            col(PlayerProfileHistory.changed_at).asc(),
            col(PlayerProfileHistory.id).asc(),
        )
    )
    return list((await db.exec(statement)).all())


async def _set_ovr_rating(*, db: AsyncSession, steamid64: int, rating: int) -> None:
    db.add(
        LeaderboardPlayer(
            scope=ModeScope.OVR,
            steamid64=steamid64,
            rating=rating,
        )
    )
    await db.commit()


async def _create_ban(
    *,
    db: AsyncSession,
    ban_id: int,
    steamid64: int,
    ban_type: BanType = BanType.BHOP_HACK,
    expires_on: datetime | None = None,
    notes: str | None = None,
) -> Ban:
    ban = Ban(
        id=ban_id,
        ban_type=ban_type,
        expires_on=expires_on,
        steamid64=steamid64,
        notes=notes,
        stats="stats",
        server_id=1,
        updated_by_id="1",
        created_at=datetime.now(UTC) - timedelta(days=1),
        updated_at=datetime.now(UTC) - timedelta(hours=1),
    )
    db.add(ban)
    await db.commit()
    await db.refresh(ban)
    return ban


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
        f"{settings.API_V1_STR}/players",
        params={"offset": 0, "limit": 3},
    )
    second_page_response = await client.get(
        f"{settings.API_V1_STR}/players",
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
    assert all("is_website_user" in item for item in first_payload["data"])


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
async def test_search_players_uses_dedicated_route(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    player = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Search Route Player",
        custom_id="search-route-player",
    )

    response = await client.get(
        f"{settings.API_V1_STR}/players/search",
        params={"q": "search-route-player"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] >= 1
    assert payload["data"][0]["steamid64"] == str(player.steamid64)


@pytest.mark.asyncio
async def test_search_players_exact_identifier_beats_higher_rated_fuzzy_match(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    exact_player = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Exact Search Player",
        custom_id="exact-search-player",
    )
    fuzzy_player = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Exact Search Player Fan",
    )
    await _set_ovr_rating(db=db, steamid64=exact_player.steamid64, rating=100)
    await _set_ovr_rating(db=db, steamid64=fuzzy_player.steamid64, rating=5000)

    response = await client.get(
        f"{settings.API_V1_STR}/players/search",
        params={"q": exact_player.custom_id},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"][0]["steamid64"] == str(exact_player.steamid64)


@pytest.mark.asyncio
async def test_search_players_uses_rating_to_break_same_relevance_tier(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    query_term = "runnertier"
    lower_rated = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name=f"{query_term} alpha",
    )
    higher_rated = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name=f"{query_term} beta",
    )
    await _set_ovr_rating(db=db, steamid64=lower_rated.steamid64, rating=50)
    await _set_ovr_rating(db=db, steamid64=higher_rated.steamid64, rating=900)

    response = await client.get(
        f"{settings.API_V1_STR}/players/search",
        params={"q": query_term},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"][0]["steamid64"] == str(higher_rated.steamid64)


@pytest.mark.asyncio
async def test_search_players_ignores_active_ban_rating_tiebreaker(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    query_term = "bannedrunnertier"
    clean_player = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name=f"{query_term} alpha",
    )
    banned_player = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name=f"{query_term} beta",
    )
    await _set_ovr_rating(db=db, steamid64=clean_player.steamid64, rating=50)
    await _set_ovr_rating(db=db, steamid64=banned_player.steamid64, rating=900)
    await _create_ban(
        db=db,
        ban_id=9_820_001,
        steamid64=banned_player.steamid64,
        expires_on=None,
    )

    response = await client.get(
        f"{settings.API_V1_STR}/players/search",
        params={"q": query_term},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"][0]["steamid64"] == str(clean_player.steamid64)


@pytest.mark.asyncio
async def test_search_players_supports_steam2_identifier(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    account_id = random_steamid64() & 0xFFFFFFFF
    steamid64 = (1 << 56) | (1 << 52) | (1 << 32) | account_id
    player = await _create_player(
        db=db,
        steamid64=steamid64,
        name="Steam2 Search Player",
    )

    response = await client.get(
        f"{settings.API_V1_STR}/players/search",
        params={"q": f"STEAM_1:{account_id % 2}:{account_id // 2}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"][0]["steamid64"] == str(player.steamid64)


@pytest.mark.asyncio
async def test_search_players_falls_back_to_vanity_slug_when_resolution_fails(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vanity_slug = "LegendSlugUnique"
    player = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name=vanity_slug,
    )

    async def _fake_resolve_vanity_url(_vanity_url: str) -> int | None:
        return None

    monkeypatch.setattr(
        player_crud,
        "_resolve_steam_vanity_url_to_steamid64",
        _fake_resolve_vanity_url,
    )

    response = await client.get(
        f"{settings.API_V1_STR}/players/search",
        params={"q": f"https://steamcommunity.com/id/{vanity_slug}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"][0]["steamid64"] == str(player.steamid64)


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
        f"{settings.API_V1_STR}/players",
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
    assert "profile_views" not in payload


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
    assert "profile_views" not in payload


@pytest.mark.asyncio
async def test_read_player_by_full_steam_profile_url_with_steamid64(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    player = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Profile URL Steam ID Player",
        custom_id="local-custom-id",
    )

    response = await client.get(
        f"{settings.API_V1_STR}/players/https://steamcommunity.com/profiles/{player.steamid64}"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["steamid64"] == str(player.steamid64)
    assert payload["custom_id"] == "local-custom-id"


@pytest.mark.asyncio
async def test_read_player_by_steam2_identifier(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    account_id = random_steamid64() & 0xFFFFFFFF
    steamid64 = (1 << 56) | (1 << 52) | (1 << 32) | account_id
    player = await _create_player(
        db=db,
        steamid64=steamid64,
        name="Steam2 Player",
        custom_id="steam2-player",
    )

    response = await client.get(
        f"{settings.API_V1_STR}/players/STEAM_1:{account_id % 2}:{account_id // 2}"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["steamid64"] == str(player.steamid64)
    assert payload["custom_id"] == "steam2-player"


@pytest.mark.asyncio
async def test_read_player_by_account_id_identifier(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    account_id = random_steamid64() & 0xFFFFFFFF
    steamid64 = (1 << 56) | (1 << 52) | (1 << 32) | account_id
    player = await _create_player(
        db=db,
        steamid64=steamid64,
        name="Account ID Player",
        custom_id="account-id-player",
    )

    response = await client.get(f"{settings.API_V1_STR}/players/{account_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["steamid64"] == str(player.steamid64)
    assert payload["custom_id"] == "account-id-player"


@pytest.mark.asyncio
async def test_read_player_by_full_steam_profile_url_with_vanity_id(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    player = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Profile URL Vanity Player",
        custom_id="local-custom-id",
    )

    async def _fake_resolve_vanity_url(_vanity_url: str) -> int | None:
        return player.steamid64

    monkeypatch.setattr(
        player_crud,
        "_resolve_steam_vanity_url_to_steamid64",
        _fake_resolve_vanity_url,
    )

    response = await client.get(
        f"{settings.API_V1_STR}/players/https://steamcommunity.com/id/Legend"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["steamid64"] == str(player.steamid64)
    assert payload["custom_id"] == "local-custom-id"


@pytest.mark.asyncio
async def test_read_player_follow_summary_accepts_full_steam_profile_url(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    target = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Profile URL Follow Summary Target",
    )
    follower_headers = await get_user_token_headers(client, random_steamid64())

    await client.put(
        f"{settings.API_V1_STR}/player-follows/players/https://steamcommunity.com/profiles/{target.steamid64}",
        headers=follower_headers,
    )

    response = await client.get(
        f"{settings.API_V1_STR}/player-follows/players/https://steamcommunity.com/profiles/{target.steamid64}/summary"
    )

    assert response.status_code == 200
    assert response.json()["follower_count"] == 1


@pytest.mark.asyncio
async def test_read_player_views_returns_profile_view_count(
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

    player_response = await client.get(f"{settings.API_V1_STR}/players/{target.steamid64}")
    response = await client.get(
        f"{settings.API_V1_STR}/players/{target.steamid64}/views"
    )

    assert player_response.status_code == 200
    assert "profile_views" not in player_response.json()
    assert response.status_code == 200
    assert response.json()["profile_views"] == 1


@pytest.mark.asyncio
async def test_read_player_includes_is_website_user(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    website_user = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Website User Player",
    )
    db.add(
        User(
            steamid64=website_user.steamid64,
            is_active=True,
            roles=[],
        )
    )
    await db.commit()

    response = await client.get(
        f"{settings.API_V1_STR}/players/{website_user.steamid64}"
    )

    assert response.status_code == 200
    assert response.json()["is_website_user"] is True


@pytest.mark.asyncio
async def test_read_player_schedules_steam_profile_sync_when_never_synced(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    player = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Missing Avatar Player",
    )
    scheduled_steamid64s: list[int] = []

    async def _fake_sync_player_steam_profile_if_due(*, steamid64: int) -> None:
        scheduled_steamid64s.append(steamid64)

    monkeypatch.setattr(
        players_api,
        "sync_player_steam_profile_if_due",
        _fake_sync_player_steam_profile_if_due,
    )

    response = await client.get(f"{settings.API_V1_STR}/players/{player.steamid64}")

    assert response.status_code == 200
    assert response.json()["avatar_hash"] is None
    assert scheduled_steamid64s == [player.steamid64]


@pytest.mark.asyncio
async def test_read_player_does_not_schedule_recent_steam_profile_sync(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    player = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Checked Avatar Player",
        steam_profile_synced_at=datetime.now(UTC),
    )
    scheduled_steamid64s: list[int] = []

    async def _fake_sync_player_steam_profile_if_due(*, steamid64: int) -> None:
        scheduled_steamid64s.append(steamid64)

    monkeypatch.setattr(
        players_api,
        "sync_player_steam_profile_if_due",
        _fake_sync_player_steam_profile_if_due,
    )

    response = await client.get(f"{settings.API_V1_STR}/players/{player.steamid64}")

    assert response.status_code == 200
    assert scheduled_steamid64s == []


@pytest.mark.asyncio
async def test_read_player_schedules_stale_steam_profile_sync(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    player = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Stale Steam Profile Player",
        avatar_hash="a" * 40,
        steam_profile_synced_at=datetime.now(UTC) - timedelta(days=8),
    )
    scheduled_steamid64s: list[int] = []

    async def _fake_sync_player_steam_profile_if_due(*, steamid64: int) -> None:
        scheduled_steamid64s.append(steamid64)

    monkeypatch.setattr(
        players_api,
        "sync_player_steam_profile_if_due",
        _fake_sync_player_steam_profile_if_due,
    )

    response = await client.get(f"{settings.API_V1_STR}/players/{player.steamid64}")

    assert response.status_code == 200
    assert scheduled_steamid64s == [player.steamid64]


@pytest.mark.asyncio
async def test_sync_player_steam_profile_if_due_updates_hash(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    player = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Avatar Update Player",
    )

    @asynccontextmanager
    async def _session_maker():
        yield db

    async def _fake_fetch_players_from_steam_api_if_available(
        steamid64s: list[int],
    ) -> dict[int, dict[str, str | bool | None]] | None:
        return {
            steamid64s[0]: {
                "name": "Avatar Update Player",
                "custom_id": None,
                "avatar_hash": "b" * 40,
                "country": None,
                "fetched": True,
            }
        }

    monkeypatch.setattr(player_steam_profile, "async_session_maker", _session_maker)
    monkeypatch.setattr(
        player_steam_profile,
        "_fetch_players_from_steam_api_if_available",
        _fake_fetch_players_from_steam_api_if_available,
    )

    await player_steam_profile.sync_player_steam_profile_if_due(
        steamid64=player.steamid64,
    )

    db.expire_all()
    refreshed = await db.get(Player, player.steamid64)
    assert refreshed is not None
    assert refreshed.avatar_hash == "b" * 40
    assert refreshed.steam_profile_synced_at is not None
    history_rows = await _get_profile_history_rows(db=db, steamid64=player.steamid64)
    assert len(history_rows) == 1
    assert history_rows[0].name == "Avatar Update Player"
    assert history_rows[0].avatar_hash is None


@pytest.mark.asyncio
async def test_sync_player_steam_profile_if_due_sets_empty_hash_when_not_found(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    player = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Deleted Steam Player",
        avatar_hash="c" * 40,
    )

    @asynccontextmanager
    async def _session_maker():
        yield db

    async def _fake_fetch_players_from_steam_api_if_available(
        _steamid64s: list[int],
    ) -> dict[int, dict[str, str | bool | None]] | None:
        return {}

    monkeypatch.setattr(player_steam_profile, "async_session_maker", _session_maker)
    monkeypatch.setattr(
        player_steam_profile,
        "_fetch_players_from_steam_api_if_available",
        _fake_fetch_players_from_steam_api_if_available,
    )

    await player_steam_profile.sync_player_steam_profile_if_due(
        steamid64=player.steamid64,
    )

    db.expire_all()
    refreshed = await db.get(Player, player.steamid64)
    assert refreshed is not None
    assert refreshed.avatar_hash == ""
    assert refreshed.steam_profile_synced_at is not None
    history_rows = await _get_profile_history_rows(db=db, steamid64=player.steamid64)
    assert len(history_rows) == 1
    assert history_rows[0].name == "Deleted Steam Player"
    assert history_rows[0].avatar_hash == "c" * 40


@pytest.mark.asyncio
async def test_sync_player_steam_profile_if_due_leaves_hash_null_on_fetch_failure(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    player = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Steam Failure Player",
    )
    fetch_calls = 0

    @asynccontextmanager
    async def _session_maker():
        yield db

    async def _fake_fetch_players_from_steam_api_if_available(
        _steamid64s: list[int],
    ) -> dict[int, dict[str, str | bool | None]] | None:
        nonlocal fetch_calls
        fetch_calls += 1
        return None

    monkeypatch.setattr(player_steam_profile, "async_session_maker", _session_maker)
    monkeypatch.setattr(
        player_steam_profile,
        "_fetch_players_from_steam_api_if_available",
        _fake_fetch_players_from_steam_api_if_available,
    )

    await player_steam_profile.sync_player_steam_profile_if_due(
        steamid64=player.steamid64,
    )
    await player_steam_profile.sync_player_steam_profile_if_due(
        steamid64=player.steamid64,
    )

    db.expire_all()
    refreshed = await db.get(Player, player.steamid64)
    assert refreshed is not None
    assert refreshed.avatar_hash is None
    assert refreshed.steam_profile_synced_at is not None
    assert fetch_calls == 1
    assert await _get_profile_history_rows(db=db, steamid64=player.steamid64) == []


@pytest.mark.asyncio
async def test_update_player_identity_fields_tracks_name_only_change(
    db: AsyncSession,
) -> None:
    player = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Before Name",
        avatar_hash="a" * 40,
    )

    await player_crud.update_player_identity_fields(
        session=db,
        player=player,
        name="After Name",
        now=datetime.now(UTC),
    )
    db.add(player)
    await db.commit()

    history_rows = await _get_profile_history_rows(db=db, steamid64=player.steamid64)
    assert len(history_rows) == 1
    assert history_rows[0].name == "Before Name"
    assert history_rows[0].avatar_hash == "a" * 40


@pytest.mark.asyncio
async def test_update_player_identity_fields_tracks_avatar_only_change(
    db: AsyncSession,
) -> None:
    player = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Avatar Only",
        avatar_hash=None,
    )

    await player_crud.update_player_identity_fields(
        session=db,
        player=player,
        avatar_hash="d" * 40,
        now=datetime.now(UTC),
    )
    db.add(player)
    await db.commit()

    history_rows = await _get_profile_history_rows(db=db, steamid64=player.steamid64)
    assert len(history_rows) == 1
    assert history_rows[0].name == "Avatar Only"
    assert history_rows[0].avatar_hash is None


@pytest.mark.asyncio
async def test_update_player_identity_fields_tracks_combined_change_once(
    db: AsyncSession,
) -> None:
    player = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Combined Before",
        avatar_hash="e" * 40,
    )

    await player_crud.update_player_identity_fields(
        session=db,
        player=player,
        name="Combined After",
        avatar_hash="f" * 40,
        now=datetime.now(UTC),
    )
    db.add(player)
    await db.commit()

    history_rows = await _get_profile_history_rows(db=db, steamid64=player.steamid64)
    assert len(history_rows) == 1
    assert history_rows[0].name == "Combined Before"
    assert history_rows[0].avatar_hash == "e" * 40


@pytest.mark.asyncio
async def test_update_player_identity_fields_skips_noop_history(
    db: AsyncSession,
) -> None:
    player = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Noop Player",
        avatar_hash="9" * 40,
    )

    await player_crud.update_player_identity_fields(
        session=db,
        player=player,
        name="Noop Player",
        avatar_hash="9" * 40,
        now=datetime.now(UTC),
    )
    db.add(player)
    await db.commit()

    assert await _get_profile_history_rows(db=db, steamid64=player.steamid64) == []


@pytest.mark.asyncio
async def test_read_players_list_includes_is_website_user(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    website_user = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Website User In List",
    )
    plain_player = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Plain Player In List",
    )
    db.add(
        User(
            steamid64=website_user.steamid64,
            is_active=True,
            roles=[],
        )
    )
    await db.commit()

    response = await client.get(
        f"{settings.API_V1_STR}/players",
        params={"offset": 0, "limit": 100},
    )

    assert response.status_code == 200
    players_by_id = {
        item["steamid64"]: item for item in response.json()["data"]
    }
    assert players_by_id[str(website_user.steamid64)]["is_website_user"] is True
    assert players_by_id[str(plain_player.steamid64)]["is_website_user"] is False


@pytest.mark.asyncio
async def test_read_player_by_identifier_returns_not_found_for_invalid_custom_id(
    client: AsyncClient,
) -> None:
    response = await client.get(f"{settings.API_V1_STR}/players/123456")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_read_player_by_identifier_does_not_match_null_custom_id_for_invalid_value(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Null Custom ID Player",
        custom_id=None,
    )

    response = await client.get(f"{settings.API_V1_STR}/players/invalid.profile")

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
    superuser_token_headers: dict[str, str],
) -> None:
    player = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Update Target",
    )

    response = await client.put(
        f"{settings.API_V1_STR}/players/{player.steamid64}",
        headers=superuser_token_headers,
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
    assert await crud.player_profile_field_change_exists(
        session=db,
        player_steamid64=steamid64,
        field=PlayerProfileField.COUNTRY,
    )


@pytest.mark.asyncio
async def test_update_player_accepts_custom_id_identifier(
    client: AsyncClient,
    db: AsyncSession,
    superuser_token_headers: dict[str, str],
) -> None:
    player = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Custom ID Update Target",
        custom_id="custom-update-target",
    )

    response = await client.put(
        f"{settings.API_V1_STR}/players/{player.custom_id}",
        headers=superuser_token_headers,
        json={"alias": "Updated Via Identifier"},
    )

    assert response.status_code == 200
    assert response.json()["alias"] == "Updated Via Identifier"


@pytest.mark.asyncio
async def test_update_player_rejects_non_superuser(
    client: AsyncClient,
    db: AsyncSession,
    normal_user_token_headers: dict[str, str],
) -> None:
    player = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Forbidden Update",
    )

    response = await client.put(
        f"{settings.API_V1_STR}/players/{player.steamid64}",
        headers=normal_user_token_headers,
        json={"alias": "Updated Alias", "country": "DE"},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_read_player_profile_history_requires_superuser(
    client: AsyncClient,
    db: AsyncSession,
    normal_user_token_headers: dict[str, str],
) -> None:
    player = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Protected History",
    )

    response = await client.get(
        f"{settings.API_V1_STR}/players/{player.steamid64}/profile-history",
        headers=normal_user_token_headers,
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_read_player_profile_history_returns_newest_first(
    client: AsyncClient,
    db: AsyncSession,
    superuser_token_headers: dict[str, str],
) -> None:
    player = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="History Current",
        custom_id="history-current",
        avatar_hash="1" * 40,
    )

    first_changed_at = datetime.now(UTC) - timedelta(minutes=2)
    second_changed_at = datetime.now(UTC) - timedelta(minutes=1)
    await crud.create_player_profile_history(
        session=db,
        player_steamid64=player.steamid64,
        name="History First",
        avatar_hash=None,
        changed_at=first_changed_at,
    )
    await crud.create_player_profile_history(
        session=db,
        player_steamid64=player.steamid64,
        name=None,
        avatar_hash="0" * 40,
        changed_at=second_changed_at,
    )
    await db.commit()

    response = await client.get(
        f"{settings.API_V1_STR}/players/{player.custom_id}/profile-history",
        headers=superuser_token_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 2
    assert payload["data"][0]["name"] is None
    assert payload["data"][0]["avatar_hash"] == "0" * 40
    assert payload["data"][1]["name"] == "History First"
    assert payload["data"][1]["avatar_hash"] is None


@pytest.mark.asyncio
async def test_update_player_locks_country_after_manual_set(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    superuser_token_headers: dict[str, str],
) -> None:
    player = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Lock Target",
    )
    steamid64 = player.steamid64

    update_response = await client.put(
        f"{settings.API_V1_STR}/players/{player.steamid64}",
        headers=superuser_token_headers,
        json={"country": "DE"},
    )
    assert update_response.status_code == 200

    async def _fake_fetch_player_from_steam_api(
        _steamid64: int,
    ) -> dict[str, str | bool | None]:
        return {
            "fetched": True,
            "name": "Lock Target",
            "custom_id": None,
            "avatar_hash": None,
            "country": "US",
        }

    monkeypatch.setattr(
        player_crud,
        "_fetch_player_from_steam_api",
        _fake_fetch_player_from_steam_api,
    )

    steam_response = await client.put(
        f"{settings.API_V1_STR}/players/{steamid64}/steam",
        headers=superuser_token_headers,
    )

    assert steam_response.status_code == 200
    payload = steam_response.json()
    assert payload["country"] == "DE"

    db.expire_all()
    refreshed = await db.get(Player, steamid64)
    assert refreshed is not None
    assert refreshed.country == "DE"
    assert await crud.player_profile_field_change_exists(
        session=db,
        player_steamid64=steamid64,
        field=PlayerProfileField.COUNTRY,
    )


@pytest.mark.asyncio
async def test_read_current_player_settings_returns_edit_status(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    steamid64 = random_steamid64()
    await _create_player(
        db=db,
        steamid64=steamid64,
        name="Settings Target",
        custom_id="settings-target",
    )
    headers = await authentication_token_from_steamid(
        client=client,
        steamid64=steamid64,
        db=db,
    )

    response = await client.get(
        f"{settings.API_V1_STR}/me/settings",
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["player"]["steamid64"] == str(steamid64)
    assert payload["player"]["name"] == "Test User"
    assert payload["player"]["primary_scope"] == "OVR"
    assert payload["alias"]["can_change"] is True
    assert payload["custom_id"]["can_change"] is True
    assert payload["country"]["can_change"] is True
    assert payload["country_locked"] is False


@pytest.mark.asyncio
async def test_update_current_player_settings_persists_changes_and_locks_country(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    steamid64 = random_steamid64()
    await _create_player(db=db, steamid64=steamid64, name="Settings Save")
    headers = await authentication_token_from_steamid(
        client=client,
        steamid64=steamid64,
        db=db,
    )

    response = await client.patch(
        f"{settings.API_V1_STR}/me/settings",
        headers=headers,
        json={
            "alias": "Saved Alias",
            "custom_id": "Saved_Custom",
            "country": "de",
            "primary_scope": "SKZ",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["player"]["alias"] == "Saved Alias"
    assert payload["player"]["custom_id"] == "saved_custom"
    assert payload["player"]["country"] == "DE"
    assert payload["player"]["primary_scope"] == "SKZ"
    assert payload["country_locked"] is True
    assert payload["country"]["can_change"] is True
    db.expire_all()
    refreshed = await db.get(Player, steamid64)
    assert refreshed is not None
    assert refreshed.alias == "Saved Alias"
    assert refreshed.custom_id == "saved_custom"
    assert refreshed.country == "DE"
    assert refreshed.primary_scope == ModeScope.SKZ
    for field in (
        PlayerProfileField.ALIAS,
        PlayerProfileField.CUSTOM_ID,
        PlayerProfileField.COUNTRY,
    ):
        assert await crud.player_profile_field_change_exists(
            session=db,
            player_steamid64=steamid64,
            field=field,
        )


@pytest.mark.asyncio
async def test_update_current_player_settings_enforces_alias_cooldown(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    steamid64 = random_steamid64()
    await _create_player(
        db=db,
        steamid64=steamid64,
        name="Alias Cooldown",
        custom_id="alias-cooldown",
    )
    await _create_profile_field_change(
        db=db,
        steamid64=steamid64,
        field=PlayerProfileField.ALIAS,
        changed_at=datetime.now(UTC),
    )
    headers = await authentication_token_from_steamid(
        client=client,
        steamid64=steamid64,
        db=db,
    )

    response = await client.patch(
        f"{settings.API_V1_STR}/me/settings",
        headers=headers,
        json={"alias": "Blocked Alias"},
    )

    assert response.status_code == 409
    assert "30 days" in response.json()["detail"]


@pytest.mark.asyncio
async def test_update_current_player_settings_enforces_custom_id_cooldown(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    steamid64 = random_steamid64()
    await _create_player(
        db=db,
        steamid64=steamid64,
        name="Custom Cooldown",
        custom_id="custom-cooldown",
    )
    await _create_profile_field_change(
        db=db,
        steamid64=steamid64,
        field=PlayerProfileField.CUSTOM_ID,
        changed_at=datetime.now(UTC),
    )
    headers = await authentication_token_from_steamid(
        client=client,
        steamid64=steamid64,
        db=db,
    )

    response = await client.patch(
        f"{settings.API_V1_STR}/me/settings",
        headers=headers,
        json={"custom_id": "new-custom-cooldown"},
    )

    assert response.status_code == 409
    assert "30 days" in response.json()["detail"]


@pytest.mark.asyncio
async def test_update_current_player_settings_allows_superuser_to_bypass_cooldowns(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    steamid64 = settings.SUPER_USER_STEAMID64
    player = await db.get(Player, steamid64)
    if player is None:
        player = await _create_player(
            db=db,
            steamid64=steamid64,
            name="Superuser Settings",
            custom_id="superuser-settings",
        )
    else:
        player.name = "Superuser Settings"
        player.custom_id = "superuser-settings"
        db.add(player)
        await db.commit()
    await _create_profile_field_change(
        db=db,
        steamid64=steamid64,
        field=PlayerProfileField.ALIAS,
        changed_at=datetime.now(UTC),
    )
    await _create_profile_field_change(
        db=db,
        steamid64=steamid64,
        field=PlayerProfileField.CUSTOM_ID,
        changed_at=datetime.now(UTC),
    )
    headers = await get_superuser_token_headers(client)

    response = await client.patch(
        f"{settings.API_V1_STR}/me/settings",
        headers=headers,
        json={"alias": "Super Alias", "custom_id": "super-bypass"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["player"]["alias"] == "Super Alias"
    assert payload["player"]["custom_id"] == "super-bypass"
    db.expire_all()
    refreshed = await db.get(Player, steamid64)
    assert refreshed is not None
    assert refreshed.alias == "Super Alias"
    assert refreshed.custom_id == "super-bypass"


@pytest.mark.asyncio
async def test_read_current_player_settings_hides_cooldowns_for_superuser(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    steamid64 = settings.SUPER_USER_STEAMID64
    player = await db.get(Player, steamid64)
    if player is None:
        player = await _create_player(
            db=db,
            steamid64=steamid64,
            name="Superuser Settings Read",
            custom_id="superuser-settings-read",
        )
    else:
        player.name = "Superuser Settings Read"
        player.custom_id = "superuser-settings-read"
        db.add(player)
        await db.commit()
    await _create_profile_field_change(
        db=db,
        steamid64=steamid64,
        field=PlayerProfileField.ALIAS,
        changed_at=datetime.now(UTC),
    )
    await _create_profile_field_change(
        db=db,
        steamid64=steamid64,
        field=PlayerProfileField.CUSTOM_ID,
        changed_at=datetime.now(UTC),
    )
    headers = await get_superuser_token_headers(client)

    response = await client.get(
        f"{settings.API_V1_STR}/me/settings",
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["alias"]["can_change"] is True
    assert payload["alias"]["next_available_at"] is None
    assert payload["custom_id"]["can_change"] is True
    assert payload["custom_id"]["next_available_at"] is None


@pytest.mark.asyncio
async def test_update_current_player_settings_rejects_custom_id_conflict(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    steamid64 = random_steamid64()
    await _create_player(db=db, steamid64=steamid64, name="Custom Conflict")
    await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Custom Owner",
        custom_id="taken-custom",
    )
    headers = await authentication_token_from_steamid(
        client=client,
        steamid64=steamid64,
        db=db,
    )

    response = await client.patch(
        f"{settings.API_V1_STR}/me/settings",
        headers=headers,
        json={"custom_id": "taken-custom"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "custom_id is already in use"


@pytest.mark.asyncio
async def test_update_current_player_settings_rejects_alias_with_non_english_characters(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    steamid64 = random_steamid64()
    await _create_player(db=db, steamid64=steamid64, name="Alias Validation")
    headers = await authentication_token_from_steamid(
        client=client,
        steamid64=steamid64,
        db=db,
    )

    response = await client.patch(
        f"{settings.API_V1_STR}/me/settings",
        headers=headers,
        json={"alias": "赛发东方"},
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["msg"] == (
        "Value error, alias can only use English letters, numbers, spaces, '-' or '_'"
    )


@pytest.mark.asyncio
async def test_update_current_player_settings_rejects_custom_id_with_spaces(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    steamid64 = random_steamid64()
    await _create_player(db=db, steamid64=steamid64, name="Custom ID Validation")
    headers = await authentication_token_from_steamid(
        client=client,
        steamid64=steamid64,
        db=db,
    )

    response = await client.patch(
        f"{settings.API_V1_STR}/me/settings",
        headers=headers,
        json={"custom_id": "bad id"},
    )

    assert response.status_code == 422
    assert (
        response.json()["detail"][0]["msg"]
        == "Value error, custom_id can only use English letters, numbers, '-' or '_'"
    )


@pytest.mark.asyncio
async def test_update_current_player_settings_rejects_clear_and_name_edits(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    steamid64 = random_steamid64()
    await _create_player(
        db=db,
        steamid64=steamid64,
        name="No Clear",
        custom_id="no-clear",
    )
    headers = await authentication_token_from_steamid(
        client=client,
        steamid64=steamid64,
        db=db,
    )

    clear_response = await client.patch(
        f"{settings.API_V1_STR}/me/settings",
        headers=headers,
        json={"alias": None},
    )
    name_response = await client.patch(
        f"{settings.API_V1_STR}/me/settings",
        headers=headers,
        json={"name": "Not Allowed"},
    )

    assert clear_response.status_code == 422
    assert name_response.status_code == 422


@pytest.mark.asyncio
async def test_update_current_player_settings_allows_country_changes_after_lock(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    steamid64 = random_steamid64()
    await _create_player(
        db=db,
        steamid64=steamid64,
        name="Country Lock",
        custom_id="country-lock",
    )
    await _create_profile_field_change(
        db=db,
        steamid64=steamid64,
        field=PlayerProfileField.COUNTRY,
        changed_at=datetime.now(UTC),
    )
    player = await db.get(Player, steamid64)
    assert player is not None
    player.country = "CA"
    db.add(player)
    await db.commit()
    headers = await authentication_token_from_steamid(
        client=client,
        steamid64=steamid64,
        db=db,
    )

    response = await client.patch(
        f"{settings.API_V1_STR}/me/settings",
        headers=headers,
        json={"country": "DE"},
    )

    assert response.status_code == 200
    assert response.json()["player"]["country"] == "DE"
    assert response.json()["country_locked"] is True
    assert response.json()["country"]["can_change"] is True

    db.expire_all()
    refreshed = await db.get(Player, steamid64)
    assert refreshed is not None
    assert refreshed.country == "DE"


@pytest.mark.asyncio
async def test_update_current_player_settings_updates_primary_scope_without_cooldown(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    steamid64 = random_steamid64()
    await _create_player(
        db=db,
        steamid64=steamid64,
        name="Primary Scope",
        custom_id="primary-scope",
    )
    await _create_profile_field_change(
        db=db,
        steamid64=steamid64,
        field=PlayerProfileField.ALIAS,
        changed_at=datetime.now(UTC),
    )
    headers = await authentication_token_from_steamid(
        client=client,
        steamid64=steamid64,
        db=db,
    )

    response = await client.patch(
        f"{settings.API_V1_STR}/me/settings",
        headers=headers,
        json={"primary_scope": "VNL"},
    )

    assert response.status_code == 200
    assert response.json()["player"]["primary_scope"] == "VNL"

    db.expire_all()
    refreshed = await db.get(Player, steamid64)
    assert refreshed is not None
    assert refreshed.primary_scope == ModeScope.VNL


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
async def test_upsert_player_from_steam_accepts_custom_id_identifier(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    normal_user_token_headers: dict[str, str],
) -> None:
    target = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Existing Target",
        custom_id="existing-target",
    )

    async def _fake_fetch_player_from_steam_api(
        _steamid64: int,
    ) -> dict[str, str | None]:
        return {
            "name": "Steam Synced Via Identifier",
            "custom_id": "existing-target",
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
        f"{settings.API_V1_STR}/players/{target.custom_id}/steam",
        headers=normal_user_token_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["steamid64"] == str(target.steamid64)
    assert payload["name"] == "Steam Synced Via Identifier"


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
async def test_upsert_player_from_steam_ignores_colliding_custom_id_for_new_player(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    normal_user_token_headers: dict[str, str],
) -> None:
    existing = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Existing Collision Owner",
        custom_id="steam-synced",
    )
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
    assert payload["custom_id"] is None

    refreshed_existing = await db.get(Player, existing.steamid64)
    refreshed_new = await db.get(Player, steamid64)
    assert refreshed_existing is not None
    assert refreshed_existing.custom_id == "steam-synced"
    assert refreshed_new is not None
    assert refreshed_new.custom_id is None


@pytest.mark.asyncio
async def test_upsert_player_from_steam_keeps_existing_custom_id_on_collision(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    normal_user_token_headers: dict[str, str],
) -> None:
    collision_owner = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Collision Owner",
        custom_id="taken-custom-id",
    )
    target = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Target Player",
        custom_id="current-custom-id",
    )

    async def _fake_fetch_player_from_steam_api(
        _steamid64: int,
    ) -> dict[str, str | None]:
        return {
            "name": "Updated Target Name",
            "custom_id": "taken-custom-id",
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
        f"{settings.API_V1_STR}/players/{target.steamid64}/steam",
        headers=normal_user_token_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["custom_id"] == "current-custom-id"
    assert payload["name"] == "Updated Target Name"

    refreshed_target = await db.get(Player, target.steamid64)
    refreshed_owner = await db.get(Player, collision_owner.steamid64)
    assert refreshed_target is not None
    assert refreshed_target.custom_id == "current-custom-id"
    assert refreshed_target.name == "Updated Target Name"
    assert refreshed_owner is not None
    assert refreshed_owner.custom_id == "taken-custom-id"


@pytest.mark.asyncio
async def test_upsert_player_from_steam_only_fills_null_custom_id(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    normal_user_token_headers: dict[str, str],
) -> None:
    target = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Target Player",
        custom_id="current-custom-id",
    )

    async def _fake_fetch_player_from_steam_api(
        _steamid64: int,
    ) -> dict[str, str | None]:
        return {
            "name": "Updated Target Name",
            "custom_id": "new-steam-custom",
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
        f"{settings.API_V1_STR}/players/{target.steamid64}/steam",
        headers=normal_user_token_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["custom_id"] == "current-custom-id"

    refreshed_target = await db.get(Player, target.steamid64)
    assert refreshed_target is not None
    assert refreshed_target.custom_id == "current-custom-id"


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

    await client.put(
        f"{settings.API_V1_STR}/player-follows/players/{target.steamid64}",
        headers=follower_headers,
    )

    response = await client.get(
        f"{settings.API_V1_STR}/player-follows/players/{target.steamid64}/summary"
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

    await client.put(
        f"{settings.API_V1_STR}/player-follows/players/{target.steamid64}",
        headers=viewer_headers,
    )

    response = await client.get(
        f"{settings.API_V1_STR}/player-follows/players/{target.steamid64}/summary",
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

    follow_response = await client.put(
        f"{settings.API_V1_STR}/player-follows/players/{target.steamid64}",
    )
    unfollow_response = await client.delete(
        f"{settings.API_V1_STR}/player-follows/players/{target.steamid64}",
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

    response = await client.put(
        f"{settings.API_V1_STR}/player-follows/players/{steamid64}",
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
        f"{settings.API_V1_STR}/player-follows/players/{target.steamid64}/followers"
    )
    following_response = await client.get(
        f"{settings.API_V1_STR}/player-follows/players/{target.steamid64}/following"
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

    follow_response = await client.put(
        f"{settings.API_V1_STR}/player-follows/players/{target.steamid64}",
        headers=viewer_headers,
    )
    unfollow_response = await client.delete(
        f"{settings.API_V1_STR}/player-follows/players/{target.steamid64}",
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
        f"{settings.API_V1_STR}/player-follows/players/{target.steamid64}/followers",
        headers=viewer_headers,
    )
    following_response = await client.get(
        f"{settings.API_V1_STR}/player-follows/players/{target.steamid64}/following",
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
        f"{settings.API_V1_STR}/player-follows/players/{missing_identifier}/summary"
    )
    follow_response = await client.put(
        f"{settings.API_V1_STR}/player-follows/players/{missing_identifier}",
        headers=normal_user_token_headers,
    )
    followers_response = await client.get(
        f"{settings.API_V1_STR}/player-follows/players/{missing_identifier}/followers",
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


@pytest.mark.asyncio
async def test_check_player_ban_status_clears_own_active_ban_and_rebuilds_leaderboard(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    player = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Ban Check Owner",
    )
    player_steamid64 = player.steamid64
    player_name = player.name
    await crud.get_or_create_user_from_steam(session=db, steamid64=player_steamid64)
    headers = await get_user_token_headers(client, player_steamid64)
    ban = await _create_ban(
        db=db,
        ban_id=9_500,
        steamid64=player_steamid64,
        expires_on=None,
        notes="locally active",
    )
    ban_id = ban.id
    ban_uuid = ban.uuid
    expired_at = datetime.now(UTC) - timedelta(hours=1)
    rebuilt_steamid64s: list[int] = []

    async def _fake_fetch(
        *,
        client: object,
        offset: int,
        limit: int,
        steamid64: int | None = None,
        created_since: datetime | None = None,
        updated_since: datetime | None = None,
    ) -> list[dict[str, object]]:
        del client, limit, created_since, updated_since
        assert steamid64 == player_steamid64
        if offset > 0:
            return []
        return [
            {
                "id": ban_id,
                "ban_type": "bhop_hack",
                "expires_on": expired_at.isoformat(),
                "ip": "203.0.113.1",
                "steamid64": str(player_steamid64),
                "player_name": player_name,
                "notes": "expired upstream",
                "stats": "stats",
                "server_id": 1,
                "updated_by_id": "1",
                "created_on": (datetime.now(UTC) - timedelta(days=2)).isoformat(),
                "updated_on": datetime.now(UTC).isoformat(),
            }
        ]

    async def _fake_rebuild(
        *,
        session: AsyncSession,
        scope_ids: list[int] | None = None,
        steamid64s: list[int] | None = None,
    ) -> tuple[int, int, int]:
        del session, scope_ids
        rebuilt_steamid64s.extend(steamid64s or [])
        return 0, 0, 0

    monkeypatch.setattr(globalapi_ban_sync, "fetch_bans_from_globalapi", _fake_fetch)
    monkeypatch.setattr(
        globalapi_ban_sync.crud,
        "rebuild_leaderboard_players",
        _fake_rebuild,
    )

    response = await client.post(
        f"{settings.API_V1_STR}/me/ban-status-checks",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["cleared_ban_count"] == 1
    assert response.json()["remaining_active_ban_count"] == 0
    assert rebuilt_steamid64s == [player_steamid64]

    db.expire_all()
    refreshed = await db.get(Ban, ban_uuid)
    assert refreshed is not None
    assert refreshed.expires_on == expired_at
    assert refreshed.notes == "expired upstream"


@pytest.mark.asyncio
async def test_check_player_ban_status_keeps_active_ban_when_globalapi_still_reports_it(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    player = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Still Banned",
    )
    player_steamid64 = player.steamid64
    player_name = player.name
    await crud.get_or_create_user_from_steam(session=db, steamid64=player_steamid64)
    headers = await get_user_token_headers(client, player_steamid64)
    ban = await _create_ban(
        db=db,
        ban_id=9_501,
        steamid64=player_steamid64,
        expires_on=None,
    )
    ban_id = ban.id
    ban_uuid = ban.uuid
    future_expiry = datetime.now(UTC) + timedelta(days=7)
    rebuilt_steamid64s: list[int] = []

    async def _fake_fetch(
        *,
        client: object,
        offset: int,
        limit: int,
        steamid64: int | None = None,
        created_since: datetime | None = None,
        updated_since: datetime | None = None,
    ) -> list[dict[str, object]]:
        del client, limit, created_since, updated_since
        assert steamid64 == player_steamid64
        if offset > 0:
            return []
        return [
            {
                "id": ban_id,
                "ban_type": "bhop_hack",
                "expires_on": future_expiry.isoformat(),
                "ip": "203.0.113.1",
                "steamid64": str(player_steamid64),
                "player_name": player_name,
                "notes": "still active upstream",
                "stats": "stats",
                "server_id": 1,
                "updated_by_id": "1",
                "created_on": (datetime.now(UTC) - timedelta(days=2)).isoformat(),
                "updated_on": datetime.now(UTC).isoformat(),
            }
        ]

    async def _fake_rebuild(
        *,
        session: AsyncSession,
        scope_ids: list[int] | None = None,
        steamid64s: list[int] | None = None,
    ) -> tuple[int, int, int]:
        del session, scope_ids
        rebuilt_steamid64s.extend(steamid64s or [])
        return 0, 0, 0

    monkeypatch.setattr(globalapi_ban_sync, "fetch_bans_from_globalapi", _fake_fetch)
    monkeypatch.setattr(
        globalapi_ban_sync.crud,
        "rebuild_leaderboard_players",
        _fake_rebuild,
    )

    response = await client.post(
        f"{settings.API_V1_STR}/me/ban-status-checks",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["cleared_ban_count"] == 0
    assert response.json()["remaining_active_ban_count"] == 1
    assert rebuilt_steamid64s == []

    db.expire_all()
    refreshed = await db.get(Ban, ban_uuid)
    assert refreshed is not None
    assert refreshed.expires_on == future_expiry


@pytest.mark.asyncio
async def test_check_player_ban_status_uses_current_user_identity(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Ignored Target",
    )
    other_steamid64 = random_steamid64()
    await _create_player(
        db=db,
        steamid64=other_steamid64,
        name="Current User",
    )
    other_headers = await get_user_token_headers(client, other_steamid64)

    async def _fake_sync(
        *,
        session: AsyncSession,
        steamid64: int,
    ) -> globalapi_ban_sync.PlayerBanSyncResult:
        del session
        assert steamid64 == other_steamid64
        return globalapi_ban_sync.PlayerBanSyncResult(
            remaining_active_ban_count=0,
            cleared_active_ban_count=0,
        )

    monkeypatch.setattr(
        me_player_actions_api,
        "sync_player_bans_from_globalapi",
        _fake_sync,
    )

    response = await client.post(
        f"{settings.API_V1_STR}/me/ban-status-checks",
        headers=other_headers,
    )

    assert response.status_code == 200
    assert response.json()["remaining_active_ban_count"] == 0


@pytest.mark.asyncio
async def test_check_player_ban_status_returns_bad_gateway_on_globalapi_failure(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    player = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Failure Owner",
    )
    await crud.get_or_create_user_from_steam(session=db, steamid64=player.steamid64)
    headers = await get_user_token_headers(client, player.steamid64)

    async def _fake_sync(
        *,
        session: AsyncSession,
        steamid64: int,
    ) -> globalapi_ban_sync.PlayerBanSyncResult:
        del session, steamid64
        raise globalapi_ban_sync.GlobalApiBanSyncError(
            "Failed to fetch bans from GlobalAPI"
        )

    monkeypatch.setattr(
        me_player_actions_api,
        "sync_player_bans_from_globalapi",
        _fake_sync,
    )

    response = await client.post(
        f"{settings.API_V1_STR}/me/ban-status-checks",
        headers=headers,
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "Failed to fetch bans from GlobalAPI"
