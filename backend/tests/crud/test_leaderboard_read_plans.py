"""Leaderboard rank work should stop at the selected page's rating boundary."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlmodel import delete

from app.crud.leaderboard_player import read_player_leaderboard
from app.models import (
    Ban,
    BanType,
    LeaderboardPlayer,
    ModeScope,
    Player,
    PlayerFriend,
    PlayerLeaderboardListQuery,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("filters", "expected_indices", "ranked_limit"),
    [
        ({}, [8, 9, 10, 11], 4),
        ({"country": "JP"}, [15, 17, 19, 21], 21),
        ({"region": "AS"}, [15, 17, 19, 21], 21),
        ({"sort_by": "points"}, [92, 91, 90, 89], 93),
        ({"friends_only": True}, [70, 80, 90], 91),
        ({"offset": 110}, [], 0),
    ],
)
async def test_leaderboard_page_ranks_preserve_filters_and_ties(
    db, monkeypatch, filters, expected_indices, ranked_limit
):
    await db.exec(delete(LeaderboardPlayer))
    base_id = 76561198001000000
    db.add_all(
        Player(
            steamid64=base_id + index,
            name=f"Rank fixture {index}",
            country="JP" if index % 2 else "DE",
        )
        for index in range(100)
    )
    await db.flush()
    db.add_all(
        LeaderboardPlayer(
            scope=ModeScope.OVR,
            steamid64=base_id + index,
            rating=100 - index // 2,
            points=index + 1,
        )
        for index in range(100)
    )
    db.add(Ban(steamid64=base_id, ban_type=BanType.OTHER))
    db.add(
        Ban(
            steamid64=base_id + 1,
            ban_type=BanType.OTHER,
            expires_at=datetime(2000, 1, 1, tzinfo=UTC),
        )
    )
    db.add_all(
        PlayerFriend(player_steamid64=base_id + 1, friend_steamid64=base_id + index)
        for index in range(10, 100, 10)
    )
    await db.flush()
    original = db.execute
    plans = []

    async def inspected(statement, *args, **kwargs):
        sql = str(
            statement.compile(
                dialect=db.get_bind().dialect, compile_kwargs={"literal_binds": True}
            )
        )
        if "row_number()" in sql:
            plans.append(
                (
                    await original(text("EXPLAIN (ANALYZE, FORMAT JSON) " + sql))
                ).scalar_one()[0]["Plan"]
            )
        return await original(statement, *args, **kwargs)

    monkeypatch.setattr(db, "execute", inspected)
    query = PlayerLeaderboardListQuery(
        **{
            "scope": ModeScope.OVR,
            "offset": 7,
            "limit": 4,
            "include_count": False,
        }
        | filters
    )
    rows, count = await read_player_leaderboard(
        session=db,
        query=query,
        friends_viewer_steamid64=base_id + 1 if query.friends_only else None,
    )
    assert count == -1
    assert [int(row.player.steamid64) - base_id for row in rows] == expected_indices
    assert [row.global_rank for row in rows] == expected_indices
    assert [row.rank for row in rows] == list(
        range(query.offset + 1, query.offset + len(rows) + 1)
    )
    assert len(plans) == 1
    pending = plans.copy()
    ranked_rows = []
    while pending:
        node = pending.pop()
        if node["Node Type"] == "WindowAgg":
            ranked_rows.append(node["Actual Rows"])
        pending.extend(node.get("Plans", []))
    assert ranked_rows and max(ranked_rows) <= ranked_limit
