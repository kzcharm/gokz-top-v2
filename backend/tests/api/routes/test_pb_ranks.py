from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.crud import record as record_crud
from app.models import Player
from tests.api.routes.test_records import (
    _create_ban,
    _create_record,
    _seed_record_dependencies,
)
from tests.utils.utils import random_steamid64

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def ranked_players(db: AsyncSession) -> list[int]:
    players = [random_steamid64() for _ in range(4)]
    await _seed_record_dependencies(
        db,
        players=list(zip(players, ["Target", "Tie", "Faster", "Banned"], strict=True)),
    )
    for player_id, country in zip(players, ["DE", "FR", "CN", "DE"], strict=True):
        player = await db.get(Player, player_id)
        assert player is not None
        player.country = country
        db.add(player)
    await db.commit()
    records = []
    for index, (player_id, time) in enumerate(
        zip(players, ["20", "20", "10", "5"], strict=True)
    ):
        record = await _create_record(
            db,
            id=989100 + index,
            steamid64=player_id,
            server_id=980300,
            mode_id=200 if index != 2 else 202,
            map_id=980200,
            stage=0,
            time=time,
            teleports=0,
        )
        records.append(record)
    # Legacy record UUIDs need not follow fixture insertion order.
    if records[0].uuid > records[1].uuid:
        players[0], players[1] = players[1], players[0]
        for player_id, country in zip(players[:2], ["DE", "FR"], strict=True):
            player = await db.get(Player, player_id)
            assert player is not None
            player.country = country
            db.add(player)
        await db.commit()
    await _create_ban(db, id=989110, steamid64=players[3], expires_on=None)
    return players


async def test_pb_ranks_are_opt_in(
    client: AsyncClient,
    ranked_players: list[int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lookup = AsyncMock(side_effect=AssertionError("Rank lookup must not run"))
    monkeypatch.setattr(record_crud, "read_pb_ranks", lookup)
    for flag in (None, "false"):
        params = {"identifier": str(ranked_players[0])}
        if flag is not None:
            params["include_ranks"] = flag
        response = await client.get("/v1/records/pb", params=params)
        assert response.status_code == 200
        assert len(response.json()) == 1
        assert response.json()[0]["rank"] is None
    lookup.assert_not_awaited()


@pytest.mark.parametrize(
    ("filters", "rank"),
    [
        ({"scope": "OVR", "type": "NUB"}, 2),
        ({"scope": "OVR", "type": "PRO"}, 2),
        ({"scope": "KZT", "type": "NUB"}, 1),
        ({"scope": "KZT", "type": "PRO"}, 1),
        ({"country": "de"}, 1),
        ({"region": "EU"}, 1),
    ],
)
async def test_pb_ranks_use_all_eligible_competitors(
    client: AsyncClient,
    ranked_players: list[int],
    filters: dict[str, str],
    rank: int,
) -> None:
    response = await client.get(
        "/v1/records/pb",
        params={
            "identifier": str(ranked_players[0]),
            "include_ranks": "true",
            "exclude_cheaters": "false",
            "limit": "1",
            **filters,
        },
    )
    assert response.status_code == 200
    [record] = response.json()
    assert record["rank"] == rank


async def test_pb_ranks_banned_targets_are_unranked_and_expired_bans_do_not_exclude(
    client: AsyncClient,
    db: AsyncSession,
    ranked_players: list[int],
) -> None:
    response = await client.get(
        "/v1/records/pb",
        params={
            "identifier": str(ranked_players[3]),
            "include_ranks": "true",
            "exclude_cheaters": "false",
        },
    )
    assert response.status_code == 200
    [record] = response.json()
    assert record["rank"] is None
    await _create_ban(
        db,
        id=989111,
        steamid64=ranked_players[2],
        expires_on=datetime.now(UTC) - timedelta(days=1),
    )
    response = await client.get(
        "/v1/records/pb",
        params={
            "identifier": str(ranked_players[2]),
            "include_ranks": "true",
        },
    )
    assert response.status_code == 200
    [record] = response.json()
    assert record["rank"] == 1


async def test_pb_ranks_bonus_pagination_and_empty_results(
    client: AsyncClient,
    db: AsyncSession,
    ranked_players: list[int],
) -> None:
    for stage in (1, 2):
        for index, player_id in enumerate(ranked_players[:2]):
            await _create_record(
                db,
                id=989120 + stage * 2 + index,
                steamid64=player_id,
                server_id=980300,
                mode_id=200,
                map_id=980200,
                stage=stage,
                time=str(40 - index * 10),
                teleports=1,
            )
    params = {
        "identifier": str(ranked_players[0]),
        "include_ranks": "true",
        "is_bonus": "true",
        "limit": "1",
        "offset": "1",
    }
    response = await client.get("/v1/records/pb", params=params)
    assert response.status_code == 200
    [record] = response.json()
    assert record["stage"] == 2
    assert record["rank"] == 2
    response = await client.get("/v1/records/pb", params={**params, "offset": "2"})
    assert response.status_code == 200 and response.json() == []


async def test_pb_ranks_map_pagination_does_not_restart_ranks(
    client: AsyncClient,
    ranked_players: list[int],
) -> None:
    response = await client.get(
        "/v1/records/pb",
        params={
            "map_id": "980200",
            "include_ranks": "true",
            "offset": "1",
            "limit": "1",
        },
    )
    assert response.status_code == 200
    [record] = response.json()
    assert record["player"]["steamid64"] == str(ranked_players[0])
    assert record["rank"] == 2


async def test_page_rank_batch_is_bounded(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import uuid

    record_uuid = uuid.uuid7()
    lookup = AsyncMock(return_value={record_uuid: 7})
    monkeypatch.setattr(record_crud, "read_pb_ranks", lookup)
    response = await client.get(
        "/v1/records/pb/ranks", params={"uuid_list": str(record_uuid)}
    )
    assert response.status_code == 200
    assert response.json() == {str(record_uuid): 7}
    lookup.assert_awaited_once()
    lookup.reset_mock()
    response = await client.get(
        "/v1/records/pb/ranks",
        params=[("uuid_list", str(uuid.uuid7())) for _ in range(51)],
    )
    assert response.status_code == 422
    lookup.assert_not_awaited()


async def test_page_ranks_match_pb_ranks(
    client: AsyncClient, ranked_players: list[int]
) -> None:
    response = await client.get(
        "/v1/records/pb",
        params={"identifier": str(ranked_players[0]), "include_ranks": "true"},
    )
    record = response.json()[0]
    ranks = await client.get(
        "/v1/records/pb/ranks", params={"uuid_list": record["uuid"]}
    )
    assert ranks.status_code == 200
    assert ranks.json() == {record["uuid"]: record["rank"]}


async def test_pb_rank_enrichment_caps_response_limit(
    client: AsyncClient, ranked_players: list[int], monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.api.v1 import records as records_api

    lookup = AsyncMock(return_value=[])
    monkeypatch.setattr(records_api, "get_pb_record_publics", lookup)
    response = await client.get(
        "/v1/records/pb",
        params={
            "identifier": str(ranked_players[0]),
            "include_ranks": "true",
            "limit": 10000,
        },
    )
    assert response.status_code == 200
    assert lookup.await_args.kwargs["limit"] == 50
