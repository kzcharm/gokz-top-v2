from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import LeaderboardPlayer, ModeScope, Player, User
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
            isWebsiteUser
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
    assert player["isWebsiteUser"] is True
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
