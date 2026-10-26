from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Record, legacy_mode_id_to_kz_mode
from tests.api.routes.test_records import _create_map, _create_player
from tests.utils.utils import random_steamid64

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def completion_history(db: AsyncSession) -> dict[str, str]:
    steamid64 = random_steamid64()
    await _create_player(
        db, steamid64=steamid64, name="First finisher", custom_id="first-finisher"
    )
    await _create_map(db, id=913901, name="kz_first_completion")
    invalid_map = await _create_map(db, id=913902, name="kz_invalid_completion")
    invalid_map.validated = False
    db.add(invalid_map)
    start = datetime(2025, 1, 1, tzinfo=UTC)
    # The fastest run is much later than the first completion. An invalid earlier
    # run, another player, and an unvalidated map must not influence the result.
    for day, mode, teleports, stage, valid, map_id, time in [
        (0, 200, 0, 0, False, 913901, "500"),
        (1, 201, 2, 0, True, 913901, "400"),
        (2, 203, 3, 0, True, 913901, "300"),
        (3, 200, 0, 0, True, 913901, "200"),
        (4, 202, 0, 0, True, 913901, "150"),
        (9, 200, 0, 0, True, 913901, "100"),
        (5, 200, 1, 1, True, 913901, "90"),
        (6, 200, 0, 1, True, 913901, "80"),
        (7, 200, 0, 2, True, 913901, "70"),
        (0, 200, 0, 0, True, 913902, "60"),
    ]:
        db.add(
            Record(
                steamid64=steamid64,
                map_id=map_id,
                mode=legacy_mode_id_to_kz_mode(mode),
                stage=stage,
                time=Decimal(time),
                teleports=teleports,
                is_valid=valid,
                created_at=start + timedelta(days=day),
            )
        )
    other = await _create_player(
        db, steamid64=random_steamid64(), name="Other finisher"
    )
    db.add(
        Record(
            steamid64=other.steamid64,
            map_id=913901,
            mode=legacy_mode_id_to_kz_mode(200),
            time=Decimal("50"),
            created_at=start,
        )
    )
    await db.commit()
    return {"identifier": str(steamid64)}


@pytest.mark.parametrize(
    ("scope", "record_type", "day"),
    [
        ("OVR", "NUB", 1),
        ("OVR", "PRO", 3),
        ("KZT", "NUB", 2),
        ("KZT", "PRO", 3),
        ("SKZ", "NUB", 1),
        ("VNL", "PRO", 4),
    ],
)
async def test_first_completions_respect_scope_type_and_validity(
    client: AsyncClient,
    completion_history: dict[str, str],
    scope: str,
    record_type: str,
    day: int,
) -> None:
    response = await client.get(
        "/v1/records/pb/first-completions",
        params={**completion_history, "scope": scope, "type": record_type},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["map_id"] == 913901
    assert data[0]["stage"] == 0
    assert datetime.fromisoformat(data[0]["first_completed_at"]) == (
        datetime(2025, 1, 1, tzinfo=UTC) + timedelta(days=day)
    )


async def test_first_completions_bonus_stage_and_identifier(
    client: AsyncClient, completion_history: dict[str, str]
) -> None:
    response = await client.get(
        "/v1/records/pb/first-completions",
        params={"identifier": "first-finisher", "is_bonus": "true"},
    )
    assert response.status_code == 200
    assert [row["stage"] for row in response.json()] == [1, 2]
    response = await client.get(
        "/v1/records/pb/first-completions",
        params={**completion_history, "is_bonus": "true", "stage": 1, "type": "PRO"},
    )
    assert response.status_code == 200
    assert response.json() == [
        {"map_id": 913901, "stage": 1, "first_completed_at": "2025-01-07T00:00:00Z"}
    ]
    response = await client.get(
        "/v1/records/pb/first-completions",
        params={**completion_history, "stage": 2},
    )
    assert [row["stage"] for row in response.json()] == [2]


async def test_first_completions_empty_unknown_and_validation(
    client: AsyncClient, db: AsyncSession
) -> None:
    player = await _create_player(db, steamid64=random_steamid64(), name="No finishes")
    url = "/v1/records/pb/first-completions"
    response = await client.get(url, params={"identifier": str(player.steamid64)})
    assert response.status_code == 200
    assert response.json() == []
    response = await client.get(url, params={"identifier": "unknown-first-finisher"})
    assert response.status_code == 404
    assert (await client.get(url)).status_code == 422
    response = await client.get(
        url, params={"identifier": str(player.steamid64), "stage": -1}
    )
    assert response.status_code == 422
