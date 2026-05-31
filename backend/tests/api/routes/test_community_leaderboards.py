from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.models import Player
from tests.utils.utils import random_steamid64

pytestmark = pytest.mark.asyncio


async def _create_player(
    *,
    db: AsyncSession,
    steamid64: int,
    name: str,
) -> Player:
    player = Player(steamid64=steamid64, name=name)
    db.add(player)
    await db.commit()
    await db.refresh(player)
    return player


async def test_read_community_leaderboard_returns_profile_views(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    target = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Community Views Target",
    )
    viewers = [
        await crud.get_or_create_user_from_steam(
            session=db,
            steamid64=random_steamid64(),
        )
        for _index in range(2)
    ]
    for viewer in viewers:
        await crud.create_player_profile_view(
            session=db,
            viewer_steamid64=viewer.steamid64,
            target_steamid64=target.steamid64,
            now=datetime(2026, 5, 4, 12, 0, tzinfo=UTC),
        )
    await crud.create_player_profile_view(
        session=db,
        viewer_steamid64=viewers[0].steamid64,
        target_steamid64=target.steamid64,
        now=datetime(2026, 5, 4, 12, 0, tzinfo=UTC) + timedelta(days=1),
    )

    response = await client.get(
        "/v1/leaderboards/community",
        params={"sort_by": "views_count"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "data": [
            {
                "rank": 1,
                "player": {
                    "steamid64": str(target.steamid64),
                    "display_name": target.name,
                },
                "views_count": 3,
                "unique_visitors": 2,
                "likes": 0,
                "unique_likers": 0,
            }
        ],
        "count": 1,
    }


async def test_read_community_leaderboard_returns_likes(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    target = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Community Likes Target",
    )
    viewer = await crud.get_or_create_user_from_steam(
        session=db,
        steamid64=random_steamid64(),
    )
    await crud.create_player_like(
        session=db,
        viewer_steamid64=viewer.steamid64,
        target_steamid64=target.steamid64,
        now=datetime(2026, 5, 4, 12, 0, tzinfo=UTC),
    )

    response = await client.get(
        "/v1/leaderboards/community",
        params={"sort_by": "likes", "include_count": "false"},
    )

    assert response.status_code == 200
    assert response.json()["count"] == -1
    assert response.json()["data"][0]["likes"] == 1
    assert response.json()["data"][0]["unique_likers"] == 1


async def test_read_community_leaderboard_filters_zero_value_sort_results(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    viewed_only = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Viewed Only API Target",
    )
    liked = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Liked API Target",
    )
    viewer = await crud.get_or_create_user_from_steam(
        session=db,
        steamid64=random_steamid64(),
    )
    await crud.create_player_profile_view(
        session=db,
        viewer_steamid64=viewer.steamid64,
        target_steamid64=viewed_only.steamid64,
        now=datetime(2026, 5, 4, 12, 0, tzinfo=UTC),
    )
    await crud.create_player_like(
        session=db,
        viewer_steamid64=viewer.steamid64,
        target_steamid64=liked.steamid64,
        now=datetime(2026, 5, 4, 12, 0, tzinfo=UTC),
    )

    response = await client.get(
        "/v1/leaderboards/community",
        params={"sort_by": "likes", "limit": "100"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert [entry["player"]["steamid64"] for entry in payload["data"]] == [
        str(liked.steamid64)
    ]


async def test_read_community_leaderboard_rejects_invalid_sort_by(
    client: AsyncClient,
) -> None:
    response = await client.get(
        "/v1/leaderboards/community",
        params={"sort_by": "records"},
    )

    assert response.status_code == 422
