from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import LeaderboardPlayer, ModeScope, Player
from app.models.utils import get_datetime_utc
from tests.utils.utils import random_steamid64

pytestmark = pytest.mark.asyncio


async def test_country_leaderboard_aggregates_activity_and_top_players(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    now = get_datetime_utc()
    players: list[Player] = []
    leaderboard_rows: list[LeaderboardPlayer] = []
    for country, base_rating in (("US", 1000), ("DE", 500)):
        for index in range(10):
            steamid64 = random_steamid64()
            players.append(
                Player(
                    steamid64=steamid64,
                    name=f"{country} Player {index}",
                    country=country,
                    last_played_at=(
                        now - timedelta(days=31) if index == 9 else now
                    ),
                )
            )
            leaderboard_rows.append(
                LeaderboardPlayer(
                    scope=ModeScope.OVR,
                    steamid64=steamid64,
                    rating=base_rating + index * 100,
                )
            )
    small_steamid64 = random_steamid64()
    players.append(
        Player(
            steamid64=small_steamid64,
            name="Small Country Player",
            country="SE",
            last_played_at=now,
        )
    )
    leaderboard_rows.append(
        LeaderboardPlayer(
            scope=ModeScope.OVR,
            steamid64=small_steamid64,
            rating=20_000,
        )
    )
    unknown_steamid64 = random_steamid64()
    players.append(
        Player(
            steamid64=unknown_steamid64,
            name="Unknown Country Player",
            country=None,
            last_played_at=now,
        )
    )
    leaderboard_rows.append(
        LeaderboardPlayer(
            scope=ModeScope.OVR,
            steamid64=unknown_steamid64,
            rating=30_000,
        )
    )
    db.add_all(players)
    await db.flush()
    db.add_all(leaderboard_rows)
    await db.commit()

    response = await client.get(
        "/v1/leaderboards/countries",
        params={"scope": "OVR"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 3
    assert [row["country"] for row in payload["data"]] == ["US", "DE", "SE"]
    assert payload["data"][0]["rank"] == 1
    assert payload["data"][0]["ranked_players"] == 10
    assert payload["data"][0]["active_players"] == 9
    assert payload["data"][0]["top_players"][0]["display_name"] == "US Player 9"
    assert payload["data"][2]["rank"] is None
    assert payload["data"][2]["ranked_players"] == 1
    assert all(row["country"] for row in payload["data"])
