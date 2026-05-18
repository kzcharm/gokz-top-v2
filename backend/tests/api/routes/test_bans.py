import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlmodel import delete
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models import Ban, BanType, Player
from tests.utils.utils import random_steamid64

pytestmark = pytest.mark.asyncio


async def _create_ban(
    db: AsyncSession,
    *,
    id: int | None,
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
    if id is not None:
        await db.exec(delete(Ban).where(Ban.id == id))
        await db.commit()
    if await db.get(Player, steamid64) is None:
        db.add(Player(steamid64=steamid64, name=player_name))
        await db.commit()
    ban = Ban(
        id=id,
        ban_type=ban_type,
        expires_on=expires_on,
        steamid64=steamid64,
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


async def _create_player(
    db: AsyncSession,
    *,
    steamid64: int,
    name: str,
    alias: str | None = None,
    avatar_hash: str | None = None,
    country: str | None = None,
) -> Player:
    player = await db.get(Player, steamid64)
    if player is None:
        player = Player(
            steamid64=steamid64,
            name=name,
            alias=alias,
            avatar_hash=avatar_hash,
            country=country,
        )
    else:
        player.name = name
        player.alias = alias
        player.avatar_hash = avatar_hash
        player.country = country
    db.add(player)
    await db.commit()
    await db.refresh(player)
    return player


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
        created_on=datetime(2026, 4, 2, tzinfo=UTC),
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
        created_on=datetime(2026, 4, 3, tzinfo=UTC),
        updated_on=datetime(2026, 4, 3, tzinfo=UTC),
    )
    await _create_player(
        db,
        steamid64=76561198000000002,
        name="Temporary",
        alias="TempAlias",
        avatar_hash="avatarhash123",
        country="DE",
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
        created_on=datetime(2026, 4, 4, tzinfo=UTC),
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
    assert v0_response.json()[0]["player_name"] == "TempAlias"

    v1_response = await client.get(
        f"{settings.API_V1_STR}/bans",
        params={"stats_contains": "pattern", "offset": 0, "limit": 2},
    )
    assert v1_response.status_code == 200
    payload = v1_response.json()
    assert payload["count"] == 3
    assert payload["data"][0]["ban_type"] == "other"
    assert payload["data"][0]["uuid"]
    assert "id" not in payload["data"][0]
    assert payload["data"][1]["player"] == {
        "steamid64": "76561198000000002",
        "display_name": "TempAlias",
    }
    assert "steamid64" not in payload["data"][1]
    assert "player_name" not in payload["data"][1]


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
    await _create_player(
        db,
        steamid64=76561198000000101,
        name="Detail",
        alias="DetailAlias",
        avatar_hash="detailhash",
    )

    response = await client.get(f"{settings.API_V1_STR}/bans/{ban.uuid}")
    assert response.status_code == 200
    assert response.json()["uuid"] == str(ban.uuid)
    assert response.json()["id"] == 1101
    assert response.json()["ban_type"] == "strafe_macro"
    assert response.json()["player"] == {
        "steamid64": "76561198000000101",
        "display_name": "DetailAlias",
    }
    assert "steamid64" not in response.json()
    assert "player_name" not in response.json()

    missing = await client.get(f"{settings.API_V1_STR}/bans/{uuid.uuid4()}")
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Ban not found"}


async def test_create_manual_ban_requires_superuser(
    client: AsyncClient,
    db: AsyncSession,
    normal_user_token_headers: dict[str, str],
) -> None:
    await _clear_bans(db)
    steamid64 = random_steamid64()
    await _create_player(
        db,
        steamid64=steamid64,
        name="Manual Ban Target",
    )

    response = await client.post(
        f"{settings.API_V1_STR}/bans",
        headers=normal_user_token_headers,
        json={
            "steamid64": str(steamid64),
            "ban_type": "bhop_macro",
            "notes": "manual ban attempt",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "The user doesn't have enough privileges"


async def test_create_manual_ban_persists_null_external_id_and_v0_excludes_it(
    client: AsyncClient,
    db: AsyncSession,
    superuser_token_headers: dict[str, str],
) -> None:
    await _clear_bans(db)
    steamid64 = random_steamid64()
    player = await _create_player(
        db,
        steamid64=steamid64,
        name="Admin Created Target",
        alias="Admin Alias",
    )

    create_response = await client.post(
        f"{settings.API_V1_STR}/bans",
        headers=superuser_token_headers,
        json={
            "steamid64": str(steamid64),
            "ban_type": "bhop_macro",
            "notes": "manual admin ban",
            "stats": "admin evidence",
        },
    )

    assert create_response.status_code == 200
    created_payload = create_response.json()
    assert created_payload["uuid"]
    assert created_payload["id"] is None
    assert created_payload["updated_by_id"] == str(settings.SUPER_USER_STEAMID64)
    assert created_payload["player"] == {
        "steamid64": str(player.steamid64),
        "display_name": "Admin Alias",
    }

    created_ban = await db.get(Ban, uuid.UUID(created_payload["uuid"]))
    assert created_ban is not None
    assert created_ban.id is None
    assert created_ban.updated_by_id == str(settings.SUPER_USER_STEAMID64)

    detail_response = await client.get(
        f"{settings.API_V1_STR}/bans/{created_payload['uuid']}"
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["uuid"] == created_payload["uuid"]
    assert detail_response.json()["id"] is None

    v1_list = await client.get(
        f"{settings.API_V1_STR}/bans",
        params={"steamid64": str(steamid64)},
    )
    assert v1_list.status_code == 200
    assert v1_list.json()["count"] == 1
    assert v1_list.json()["data"][0]["uuid"] == created_payload["uuid"]
    assert "id" not in v1_list.json()["data"][0]

    v0_list = await client.get("/v0/bans", params={"steamid64": str(steamid64)})
    assert v0_list.status_code == 200
    assert v0_list.json() == []
