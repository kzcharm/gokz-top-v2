import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.v1 import graphql as graphql_api
from app.models import (
    Ban,
    BanType,
    LeaderboardPlayer,
    Map,
    ModeScope,
    Player,
    Server,
    ServerGlobalapi,
    ServerGroup,
    ServerLiveStatus,
    ServerStatus,
    User,
    get_datetime_utc,
)
from app.models.player_profile_view import PlayerProfileView
from tests.utils.utils import random_steamid64

pytestmark = pytest.mark.asyncio


async def _post_graphql(
    client: AsyncClient,
    *,
    query: str,
    variables: dict[str, object] | None = None,
) -> dict[str, object]:
    response = await client.post(
        "/v1/graphql",
        json={
            "query": query,
            "variables": variables or {},
        },
    )
    assert response.status_code == 200
    return response.json()


async def test_graphql_player_presence_uses_only_fresh_public_online_rosters(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    now = get_datetime_utc()
    cases = [
        (True, ServerStatus.ENABLED, True, now, True),
        (False, ServerStatus.ENABLED, True, now, False),
        (True, ServerStatus.DISABLED, True, now, False),
        (True, ServerStatus.ENABLED, False, now, False),
        (True, ServerStatus.ENABLED, True, now - timedelta(minutes=2), False),
    ]
    steamid64s = []
    for index, (public, status, online, updated_at, _expected) in enumerate(cases):
        steamid64 = random_steamid64()
        steamid64s.append(steamid64)
        db.add(Player(steamid64=steamid64, name=f"Presence {index}"))
        server = Server(
            ip="127.0.0.1", port=27015 + index, is_public=public, status=status
        )
        db.add(server)
        await db.flush()
        db.add(
            ServerLiveStatus(
                server_id=server.id,
                is_online=online,
                updated_at=updated_at,
                players=[{"steamid64": str(steamid64), "name": f"Presence {index}"}],
            )
        )
    unlisted = random_steamid64()
    db.add(Player(steamid64=unlisted, name="Not on a server"))
    steamid64s.append(unlisted)
    await db.commit()
    payload = await _post_graphql(
        client,
        query="""
        query Players($steamid64s: [ID!]!) {
          players(steamid64s: $steamid64s) { steamid64 isOnline }
        }
        """,
        variables={"steamid64s": [str(value) for value in steamid64s]},
    )
    assert payload.get("errors") is None
    assert [player["isOnline"] for player in payload["data"]["players"]] == [
        case[4] for case in cases
    ] + [False]


async def test_online_player_lookup_skips_empty_input(db: AsyncSession) -> None:
    assert (
        await graphql_api.server_crud.load_online_player_steamid64s(
            session=db, steamid64s=[]
        )
        == set()
    )


async def test_player_display_roles_recognize_ownership_without_changing_account_roles(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    group_owner, global_owner, admin_owner = [random_steamid64() for _ in range(3)]
    for steamid64 in (group_owner, global_owner, admin_owner):
        db.add(Player(steamid64=steamid64, name="Server owner"))
    website_user = User(steamid64=group_owner, roles=[])
    admin_user = User(steamid64=admin_owner, roles=["admin"])
    db.add(website_user)
    db.add(admin_user)
    await db.flush()
    db.add(
        ServerGroup(
            name=f"Owner {group_owner}",
            custom_id=f"owner-{group_owner}",
            api_key=str(group_owner),
            owner_steamid64=group_owner,
        )
    )
    db.add(
        ServerGroup(
            name=f"Owner {admin_owner}",
            custom_id=f"owner-{admin_owner}",
            api_key=str(admin_owner),
            owner_steamid64=admin_owner,
        )
    )
    db.add(
        ServerGlobalapi(id=global_owner % 1_000_000_000, owner_steamid64=global_owner)
    )
    await db.commit()
    payload = await _post_graphql(
        client,
        query="""
        query Players($steamid64s: [ID!]!) {
          players(steamid64s: $steamid64s) { steamid64 roles }
        }
        """,
        variables={
            "steamid64s": [
                str(value) for value in (group_owner, global_owner, admin_owner)
            ]
        },
    )
    assert payload.get("errors") is None
    assert [player["roles"] for player in payload["data"]["players"]] == [
        ["SERVER_OWNER"],
        None,
        ["ADMIN", "SERVER_OWNER"],
    ]
    await db.refresh(website_user)
    await db.refresh(admin_user)
    assert website_user.roles == []
    assert admin_user.roles == ["admin"]
    response = await client.get(f"/v1/players/{group_owner}")
    assert response.status_code == 200
    assert response.json()["roles"] == ["server_owner"]
    response = await client.get(f"/v1/players/{global_owner}")
    assert response.status_code == 200
    assert response.json()["roles"] is None
    db.add(User(steamid64=global_owner, roles=[]))
    await db.commit()
    response = await client.get(f"/v1/players/{global_owner}")
    assert response.status_code == 200
    assert response.json()["roles"] == ["server_owner"]


async def test_graphql_player_fetches_by_steamid64_and_custom_id(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    steamid64 = random_steamid64()
    viewer_steamid64 = random_steamid64()
    db.add(
        Player(
            steamid64=steamid64,
            name="Canonical Name",
            alias="Alias Name",
            custom_id="alias-name",
            country="DE",
            primary_scope=ModeScope.SKZ,
            last_played_at=datetime(2099, 1, 2, tzinfo=UTC),
        )
    )
    db.add(Player(steamid64=viewer_steamid64, name="Viewer"))
    db.add(User(steamid64=steamid64))
    db.add(User(steamid64=viewer_steamid64))
    await db.flush()
    db.add(
        LeaderboardPlayer(
            scope=ModeScope.SKZ,
            steamid64=steamid64,
            rating=32564,
        )
    )
    db.add(
        PlayerProfileView(
            viewer_steamid64=viewer_steamid64,
            target_steamid64=steamid64,
            view_date=datetime(2099, 1, 3, tzinfo=UTC).date(),
            created_at=datetime(2099, 1, 3, tzinfo=UTC),
        )
    )
    await db.commit()

    payload = await _post_graphql(
        client,
        query="""
        query PlayerByIdentifier($identifier: String!) {
          player(identifier: $identifier) {
            steamid64
            displayName
            name
            alias
            customId
            country
            primaryScope
            rating
            roles
            profileViews
            lastPlayedAt
          }
        }
        """,
        variables={"identifier": "alias-name"},
    )

    assert payload.get("errors") is None
    player = payload["data"]["player"]
    assert player["steamid64"] == str(steamid64)
    assert player["displayName"] == "Alias Name"
    assert player["name"] == "Canonical Name"
    assert player["alias"] == "Alias Name"
    assert player["customId"] == "alias-name"
    assert player["country"] == "DE"
    assert player["primaryScope"] == "SKZ"
    assert player["rating"] > 0
    assert player["roles"] == []
    assert player["profileViews"] == 1
    assert player["lastPlayedAt"] == "2099-01-02T00:00:00+00:00"

    payload = await _post_graphql(
        client,
        query="""
        query PlayerByIdentifier($identifier: String!) {
          player(identifier: $identifier) {
            steamid64
            displayName
          }
        }
        """,
        variables={"identifier": str(steamid64)},
    )
    assert payload["data"]["player"]["steamid64"] == str(steamid64)
    assert payload["data"]["player"]["displayName"] == "Alias Name"


async def test_graphql_players_batch_preserves_order_and_returns_null_for_unknown_ids(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    alpha = random_steamid64()
    beta = random_steamid64()
    db.add(Player(steamid64=alpha, name="Alpha"))
    db.add(Player(steamid64=beta, name="Beta", alias="Beta Alias"))
    await db.commit()

    payload = await _post_graphql(
        client,
        query="""
        query PlayersBatch($steamid64s: [ID!]!) {
          players(steamid64s: $steamid64s) {
            steamid64
            displayName
          }
        }
        """,
        variables={
            "steamid64s": [str(beta), str(random_steamid64()), str(alpha)],
        },
    )

    players = payload["data"]["players"]
    assert players[0]["steamid64"] == str(beta)
    assert players[0]["displayName"] == "Beta Alias"
    assert players[1] is None
    assert players[2]["steamid64"] == str(alpha)
    assert players[2]["displayName"] == "Alpha"


async def test_graphql_map_images_batches_and_preserves_input_order(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db.add(Map(id=9_820_001, name="kz_graphql_beta", workshop_id=222))
    await db.commit()
    requested_workshop_ids: list[str] = []

    async def _fake_get_cached_workshop_preview_urls(
        *,
        session: AsyncSession,
        workshop_ids: list[str],
    ) -> dict[str, str | None]:
        assert session is not None
        requested_workshop_ids.extend(workshop_ids)
        return {
            "111": "https://steam.example/alpha.jpg",
            "222": "https://steam.example/beta.jpg",
        }

    monkeypatch.setattr(
        graphql_api,
        "get_cached_workshop_preview_urls",
        _fake_get_cached_workshop_preview_urls,
    )

    payload = await _post_graphql(
        client,
        query="""
        query MapImages($inputs: [MapImageInput!]!) {
          mapImages(inputs: $inputs) {
            mapName
            workshopId
            previewUrl
          }
        }
        """,
        variables={
            "inputs": [
                {"mapName": "kz_graphql_alpha", "workshopId": "111"},
                {"mapName": "kz_graphql_beta"},
                {"mapName": "kz_graphql_missing", "workshopId": "invalid"},
                {"mapName": "kz_graphql_alpha", "workshopId": "111"},
            ]
        },
    )

    assert payload.get("errors") is None
    assert requested_workshop_ids == ["111", "222", "111"]
    assert payload["data"]["mapImages"] == [
        {
            "mapName": "kz_graphql_alpha",
            "workshopId": "111",
            "previewUrl": "https://steam.example/alpha.jpg",
        },
        {
            "mapName": "kz_graphql_beta",
            "workshopId": "222",
            "previewUrl": "https://steam.example/beta.jpg",
        },
        {
            "mapName": "kz_graphql_missing",
            "workshopId": None,
            "previewUrl": None,
        },
        {
            "mapName": "kz_graphql_alpha",
            "workshopId": "111",
            "previewUrl": "https://steam.example/alpha.jpg",
        },
    ]


async def test_graphql_players_schedule_non_blocking_steam_profile_sync(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    steamid64 = random_steamid64()
    db.add(Player(steamid64=steamid64, name=str(steamid64)))
    await db.commit()
    scheduled_steamid64s: list[list[int]] = []

    async def _fake_sync_player_steam_profiles_if_due(*, steamid64s: list[int]) -> None:
        scheduled_steamid64s.append(steamid64s)

    monkeypatch.setattr(
        graphql_api,
        "sync_player_steam_profiles_if_due",
        _fake_sync_player_steam_profiles_if_due,
    )

    payload = await _post_graphql(
        client,
        query="""
        query PlayersBatch($steamid64s: [ID!]!) {
          players(steamid64s: $steamid64s) {
            steamid64
          }
        }
        """,
        variables={"steamid64s": [str(steamid64)]},
    )

    assert payload.get("errors") is None
    await asyncio.sleep(0)
    assert scheduled_steamid64s == [[steamid64]]


async def test_graphql_player_rating_uses_primary_scope_and_explicit_scope_override(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    steamid64 = random_steamid64()
    db.add(
        Player(
            steamid64=steamid64,
            name="Scoped Rating",
            primary_scope=ModeScope.SKZ,
        )
    )
    await db.flush()
    db.add(
        LeaderboardPlayer(
            scope=ModeScope.SKZ,
            steamid64=steamid64,
            rating=32564,
        )
    )
    db.add(
        LeaderboardPlayer(
            scope=ModeScope.OVR,
            steamid64=steamid64,
            rating=41052,
        )
    )
    await db.commit()

    payload = await _post_graphql(
        client,
        query="""
        query PlayerRating($identifier: String!, $scope: ModeScope) {
          player(identifier: $identifier) {
            primaryScope
            defaultRating: rating
            explicitRating: rating(scope: $scope)
          }
        }
        """,
        variables={"identifier": str(steamid64), "scope": "OVR"},
    )

    player = payload["data"]["player"]
    assert player["primaryScope"] == "SKZ"
    assert player["defaultRating"] != player["explicitRating"]
    assert player["defaultRating"] > 0
    assert player["explicitRating"] > 0


async def test_graphql_player_rating_returns_zero_when_scope_has_no_rating(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    steamid64 = random_steamid64()
    db.add(
        Player(
            steamid64=steamid64,
            name="Unrated Scope",
            primary_scope=ModeScope.VNL,
        )
    )
    await db.commit()

    payload = await _post_graphql(
        client,
        query="""
        query PlayerRating($identifier: String!) {
          player(identifier: $identifier) {
            rating
          }
        }
        """,
        variables={"identifier": str(steamid64)},
    )

    assert payload["data"]["player"]["rating"] == 0


async def test_graphql_player_rating_returns_zero_for_active_ban(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    steamid64 = random_steamid64()
    db.add(
        Player(
            steamid64=steamid64,
            name="Banned Rated Player",
            primary_scope=ModeScope.KZT,
        )
    )
    await db.flush()
    db.add(
        LeaderboardPlayer(
            scope=ModeScope.KZT,
            steamid64=steamid64,
            rating=32564,
        )
    )
    db.add(
        Ban(
            id=9_810_001,
            ban_type=BanType.BHOP_HACK,
            expires_on=None,
            steamid64=steamid64,
            notes="cheater",
            stats="stats",
            server_id=1,
            updated_by_id="1",
            created_at=datetime(2099, 1, 3, tzinfo=UTC),
            updated_at=datetime(2099, 1, 3, tzinfo=UTC),
        )
    )
    await db.commit()

    payload = await _post_graphql(
        client,
        query="""
        query PlayerRating($identifier: String!) {
          player(identifier: $identifier) {
            rating
          }
        }
        """,
        variables={"identifier": str(steamid64)},
    )

    assert payload["data"]["player"]["rating"] == 0


async def test_graphql_search_players_returns_expected_count_and_display_name(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    alpha = random_steamid64()
    beta = random_steamid64()
    db.add(Player(steamid64=alpha, name="Alpha Runner", custom_id="alpha-runner"))
    db.add(
        Player(
            steamid64=beta,
            name="Beta Runner",
            alias="Beta Unique Search Result",
        )
    )
    await db.commit()

    payload = await _post_graphql(
        client,
        query="""
        query SearchPlayers($q: String!, $limit: Int!) {
          searchPlayers(q: $q, limit: $limit) {
            count
            data {
              steamid64
              displayName
              customId
            }
          }
        }
        """,
        variables={"q": "beta unique search result", "limit": 10},
    )

    result = payload["data"]["searchPlayers"]
    assert result["count"] == 1
    assert result["data"] == [
        {
            "steamid64": str(beta),
            "displayName": "Beta Unique Search Result",
            "customId": None,
        }
    ]


async def test_graphql_map_images_prefers_local_and_only_fetches_missing_workshop(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "MAP_IMAGE_STORAGE_DIR", tmp_path)
    (tmp_path / "kz_local.webp").write_bytes(b"local image")
    previews = AsyncMock(return_value={"222": "https://steam.example/222.jpg"})
    monkeypatch.setattr(graphql_api, "get_cached_workshop_preview_urls", previews)
    payload = await _post_graphql(
        client,
        query="""
        query MapImages($inputs: [MapImageInput!]!) {
          mapImages(inputs: $inputs) { mapName workshopId previewUrl }
        }
    """,
        variables={
            "inputs": [
                {"mapName": "kz_local", "workshopId": "111"},
                {"mapName": "kz_missing", "workshopId": "222"},
                {"mapName": "kz_local", "workshopId": "111"},
                {"mapName": "kz_unknown"},
            ]
        },
    )
    assert not payload.get("errors")
    images = payload["data"]["mapImages"]
    assert images[0]["previewUrl"].endswith("/v1/maps/images/kz_local.webp")
    assert images[1]["previewUrl"] == "https://steam.example/222.jpg"
    assert images[0] == images[2]
    assert images[3]["previewUrl"] is None
    assert previews.await_args.kwargs["workshop_ids"] == ["222"]
