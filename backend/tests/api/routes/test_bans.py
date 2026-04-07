from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlmodel import delete
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models import Ban, BanType

pytestmark = pytest.mark.asyncio


async def _create_ban(
    db: AsyncSession,
    *,
    id: int,
    ban_type: BanType,
    steamid64: int,
    expires_on: datetime | None,
    player_name: str,
    notes: str | None = None,
    stats: str | None = None,
    server_id: int | None = None,
    created_on: datetime | None = None,
    updated_on: datetime | None = None,
) -> Ban:
    await db.exec(delete(Ban).where(Ban.id == id))
    await db.commit()
    ban = Ban(
        id=id,
        ban_type=ban_type,
        expires_on=expires_on,
        steamid64=steamid64,
        player_name=player_name,
        notes=notes,
        stats=stats,
        server_id=server_id,
        updated_by_id=str(server_id or 0),
        created_on=created_on or datetime(2026, 4, 1, tzinfo=UTC),
        updated_on=updated_on or datetime(2026, 4, 1, tzinfo=UTC),
    )
    db.add(ban)
    await db.commit()
    await db.refresh(ban)
    return ban


async def _clear_bans(db: AsyncSession) -> None:
    await db.exec(delete(Ban))
    await db.commit()


async def test_read_bans_v0_and_v1_list_filters_and_shapes(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    await _clear_bans(db)
    now = datetime.now(UTC)
    expired = now - timedelta(days=1)
    active = now + timedelta(days=30)
    await _create_ban(
        db,
        id=1001,
        ban_type=BanType.BHOP_HACK,
        steamid64=76561198000000001,
        expires_on=None,
        player_name="Permanent",
        notes="macro evidence",
        stats="pattern A",
        server_id=1,
        updated_on=datetime(2026, 4, 2, tzinfo=UTC),
    )
    await _create_ban(
        db,
        id=1002,
        ban_type=BanType.BHOP_MACRO,
        steamid64=76561198000000002,
        expires_on=active,
        player_name="Temporary",
        notes="scroll pattern",
        stats="pattern B",
        server_id=2,
        updated_on=datetime(2026, 4, 3, tzinfo=UTC),
    )
    await _create_ban(
        db,
        id=1003,
        ban_type=BanType.OTHER,
        steamid64=76561198000000003,
        expires_on=expired,
        player_name="Expired",
        notes="old note",
        stats="pattern C",
        server_id=3,
        updated_on=datetime(2026, 4, 4, tzinfo=UTC),
    )

    v0_response = await client.get(
        "/v0/bans",
        params=[
            ("ban_types_list", "bhop_hack"),
            ("ban_types_list", "bhop_macro"),
            ("notes_contains", "pattern"),
            ("is_expired", "false"),
        ],
    )
    assert v0_response.status_code == 200
    assert [row["id"] for row in v0_response.json()] == [1002]
    assert v0_response.json()[0]["steamid64"] == "76561198000000002"

    v1_response = await client.get(
        f"{settings.API_V1_STR}/bans",
        params={"stats_contains": "pattern", "offset": 0, "limit": 2},
    )
    assert v1_response.status_code == 200
    payload = v1_response.json()
    assert payload["count"] == 3
    assert [row["id"] for row in payload["data"]] == [1003, 1002]
    assert payload["data"][0]["ban_type"] == "other"
    assert payload["data"][1]["steamid64"] == "76561198000000002"


async def test_read_ban_v1_detail_and_missing(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    await _clear_bans(db)
    ban = await _create_ban(
        db,
        id=1101,
        ban_type=BanType.STRAFE_MACRO,
        steamid64=76561198000000101,
        expires_on=None,
        player_name="Detail",
        notes="detail note",
        stats="detail stats",
        server_id=99,
    )

    response = await client.get(f"{settings.API_V1_STR}/bans/{ban.id}")
    assert response.status_code == 200
    assert response.json()["id"] == 1101
    assert response.json()["ban_type"] == "strafe_macro"
    assert response.json()["player_name"] == "Detail"

    missing = await client.get(f"{settings.API_V1_STR}/bans/999999")
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Ban not found"}
