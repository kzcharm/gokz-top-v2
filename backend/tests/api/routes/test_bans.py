import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlmodel import delete
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models import Ban, BanType, Player, ServerGlobalapi
from tests.utils.utils import random_steamid64

pytestmark = pytest.mark.asyncio


async def _create_ban(
    db: AsyncSession,
    *,
    id: int | None,
    ban_type: BanType,
    steamid64: int,
    expires_at: datetime | None,
    player_name: str,
    notes: str | None = None,
    stats: str | None = None,
    server_id: int | None = None,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
    updated_by_steamid64: int | None = None,
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
        expires_at=expires_at,
        steamid64=steamid64,
        notes=notes,
        stats=stats,
        server_id=server_id,
        updated_by_steamid64=updated_by_steamid64,
        created_at=created_at or datetime(2026, 4, 1, tzinfo=UTC),
        updated_at=updated_at or datetime(2026, 4, 1, tzinfo=UTC),
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


async def _create_server(
    db: AsyncSession,
    *,
    server_id: int,
    name: str,
) -> ServerGlobalapi:
    server = await db.get(ServerGlobalapi, server_id)
    if server is None:
        server = ServerGlobalapi(id=server_id, name=name)
    else:
        server.name = name
    db.add(server)
    await db.commit()
    await db.refresh(server)
    return server


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
        expires_at=None,
        player_name="Permanent",
        notes="macro evidence",
        stats="pattern A",
        server_id=1,
        created_at=datetime(2026, 4, 2, tzinfo=UTC),
        updated_at=datetime(2026, 4, 2, tzinfo=UTC),
    )
    await _create_ban(
        db,
        id=1002,
        ban_type=BanType.BHOP_MACRO,
        steamid64=76561198000000002,
        expires_at=active,
        player_name="Temporary",
        notes="scroll pattern",
        stats="pattern B",
        server_id=2,
        created_at=datetime(2026, 4, 3, tzinfo=UTC),
        updated_at=datetime(2026, 4, 3, tzinfo=UTC),
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
        expires_at=expired,
        player_name="Expired",
        notes="old note",
        stats="pattern C",
        server_id=3,
        created_at=datetime(2026, 4, 4, tzinfo=UTC),
        updated_at=datetime(2026, 4, 4, tzinfo=UTC),
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
    assert payload["data"][0]["id"] == 1003
    assert "updated_by_steamid64" not in payload["data"][0]
    assert "updated_by_player" not in payload["data"][0]
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
        expires_at=None,
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
    assert "updated_by_steamid64" not in response.json()
    assert "updated_by_player" not in response.json()
    assert "steamid64" not in response.json()
    assert "player_name" not in response.json()

    missing = await client.get(f"{settings.API_V1_STR}/bans/{uuid.uuid4()}")
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Ban not found"}


async def test_read_bans_v1_q_matches_identifiers_and_player_text(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    await _clear_bans(db)
    steamid64 = random_steamid64()
    ban = await _create_ban(
        db,
        id=12001,
        ban_type=BanType.BHOP_MACRO,
        steamid64=steamid64,
        expires_at=None,
        player_name="Search Target",
        notes="searchable",
    )
    await _create_player(
        db,
        steamid64=steamid64,
        name="Search Target",
        alias="Needle Alias",
    )

    for query in (str(ban.uuid), str(steamid64), "12001", "needle"):
        response = await client.get(f"{settings.API_V1_STR}/bans", params={"q": query})

        assert response.status_code == 200
        assert response.json()["count"] == 1
        assert response.json()["data"][0]["uuid"] == str(ban.uuid)


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


async def test_create_manual_ban_allows_admin_role(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    await _clear_bans(db)
    steamid64 = random_steamid64()
    await _create_player(
        db,
        steamid64=steamid64,
        name="Admin Ban Target",
    )
    admin_auth = await client.post(
        f"{settings.API_V1_STR}/private/auth/session",
        json={
            "steamid64": random_steamid64(),
            "roles": ["admin"],
            "is_active": True,
            "name": "Admin Ban Moderator",
        },
    )
    admin_headers = {
        "Authorization": f"Bearer {admin_auth.json()['access_token']}"
    }

    response = await client.post(
        f"{settings.API_V1_STR}/bans",
        headers=admin_headers,
        json={
            "steamid64": str(steamid64),
            "ban_type": "bhop_macro",
            "notes": "manual admin ban",
        },
    )

    assert response.status_code == 200
    assert response.json()["id"] is None


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
            "ban_type": "boosting",
            "notes": "manual admin ban",
            "stats": "admin evidence",
        },
    )

    assert create_response.status_code == 200
    created_payload = create_response.json()
    assert created_payload["uuid"]
    assert created_payload["id"] is None
    assert created_payload["ban_type"] == "boosting"
    assert created_payload["updated_by_steamid64"] == str(
        settings.SUPER_USER_STEAMID64
    )
    assert created_payload["player"] == {
        "steamid64": str(player.steamid64),
        "display_name": "Admin Alias",
    }

    created_ban = await db.get(Ban, uuid.UUID(created_payload["uuid"]))
    assert created_ban is not None
    assert created_ban.id is None
    assert created_ban.updated_by_steamid64 == settings.SUPER_USER_STEAMID64

    detail_response = await client.get(
        f"{settings.API_V1_STR}/bans/{created_payload['uuid']}"
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["uuid"] == created_payload["uuid"]
    assert detail_response.json()["id"] is None
    assert "updated_by_steamid64" not in detail_response.json()

    v1_list = await client.get(
        f"{settings.API_V1_STR}/bans",
        params={"steamid64": str(steamid64)},
    )
    assert v1_list.status_code == 200
    assert v1_list.json()["count"] == 1
    assert v1_list.json()["data"][0]["uuid"] == created_payload["uuid"]
    assert v1_list.json()["data"][0]["id"] is None

    v0_list = await client.get("/v0/bans", params={"steamid64": str(steamid64)})
    assert v0_list.status_code == 200
    assert v0_list.json() == []


async def test_read_bans_v1_admin_includes_updater_player(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    await _clear_bans(db)
    updater_steamid64 = random_steamid64()
    await _create_player(
        db,
        steamid64=updater_steamid64,
        name="Updater",
        alias="Updater Alias",
    )
    target_steamid64 = random_steamid64()
    await _create_player(db, steamid64=target_steamid64, name="Target")
    ban = await _create_ban(
        db,
        id=None,
        ban_type=BanType.BHOP_MACRO,
        steamid64=target_steamid64,
        expires_at=None,
        player_name="Target",
        updated_by_steamid64=updater_steamid64,
    )

    admin_auth = await client.post(
        f"{settings.API_V1_STR}/private/auth/session",
        json={
            "steamid64": updater_steamid64,
            "roles": ["admin"],
            "is_active": True,
            "name": "Updater",
        },
    )
    admin_headers = {
        "Authorization": f"Bearer {admin_auth.json()['access_token']}"
    }

    list_response = await client.get(
        f"{settings.API_V1_STR}/bans",
        headers=admin_headers,
        params={"steamid64": str(target_steamid64)},
    )
    assert list_response.status_code == 200
    assert list_response.json()["data"][0]["updated_by_steamid64"] == str(
        updater_steamid64
    )
    assert list_response.json()["data"][0]["updated_by_player"] == {
        "steamid64": str(updater_steamid64),
        "display_name": "Updater Alias",
    }

    detail_response = await client.get(
        f"{settings.API_V1_STR}/bans/{ban.uuid}",
        headers=admin_headers,
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["updated_by_steamid64"] == str(updater_steamid64)
    assert detail_response.json()["updated_by_player"] == {
        "steamid64": str(updater_steamid64),
        "display_name": "Updater Alias",
    }


async def test_read_bans_v1_exposes_server_updater_to_all_users_but_admin_player_only(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    await _clear_bans(db)
    server_id = 987_654
    await _create_server(db, server_id=server_id, name="KZCharm Test Server")
    updater_steamid64 = random_steamid64()
    await _create_player(
        db,
        steamid64=updater_steamid64,
        name="Hidden Updater",
        alias="Hidden Alias",
    )
    target_steamid64 = random_steamid64()
    await _create_player(db, steamid64=target_steamid64, name="Server Ban Target")
    ban = await _create_ban(
        db,
        id=987_654,
        ban_type=BanType.BHOP_MACRO,
        steamid64=target_steamid64,
        expires_at=None,
        player_name="Server Ban Target",
        server_id=server_id,
        updated_by_steamid64=updater_steamid64,
    )

    public_response = await client.get(
        f"{settings.API_V1_STR}/bans",
        params={"steamid64": str(target_steamid64)},
    )

    assert public_response.status_code == 200
    public_ban = public_response.json()["data"][0]
    assert public_ban["uuid"] == str(ban.uuid)
    assert public_ban["server"] == {
        "id": server_id,
        "name": "KZCharm Test Server",
    }
    assert "updated_by_steamid64" not in public_ban
    assert "updated_by_player" not in public_ban

    admin_auth = await client.post(
        f"{settings.API_V1_STR}/private/auth/session",
        json={
            "steamid64": updater_steamid64,
            "roles": ["admin"],
            "is_active": True,
            "name": "Hidden Updater",
        },
    )
    admin_headers = {
        "Authorization": f"Bearer {admin_auth.json()['access_token']}"
    }
    admin_response = await client.get(
        f"{settings.API_V1_STR}/bans/{ban.uuid}",
        headers=admin_headers,
    )

    assert admin_response.status_code == 200
    admin_ban = admin_response.json()
    assert admin_ban["server"] == {
        "id": server_id,
        "name": "KZCharm Test Server",
    }
    assert admin_ban["updated_by_steamid64"] == str(updater_steamid64)
    assert admin_ban["updated_by_player"] == {
        "steamid64": str(updater_steamid64),
        "display_name": "Hidden Alias",
    }


async def test_patch_ban_updates_fields_and_supports_unban(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    await _clear_bans(db)
    target_steamid64 = random_steamid64()
    await _create_player(db, steamid64=target_steamid64, name="Patch Target")
    moderator_steamid64 = random_steamid64()
    await _create_player(
        db,
        steamid64=moderator_steamid64,
        name="Patch Admin",
        alias="Patch Alias",
    )
    ban = await _create_ban(
        db,
        id=1201,
        ban_type=BanType.BHOP_HACK,
        steamid64=target_steamid64,
        expires_at=datetime(2026, 5, 10, tzinfo=UTC),
        player_name="Patch Target",
        notes="before",
        created_at=datetime(2026, 5, 1, tzinfo=UTC),
        updated_at=datetime(2026, 5, 1, tzinfo=UTC),
    )

    admin_auth = await client.post(
        f"{settings.API_V1_STR}/private/auth/session",
        json={
            "steamid64": moderator_steamid64,
            "roles": ["admin"],
            "is_active": True,
            "name": "Patch Admin",
        },
    )
    admin_headers = {
        "Authorization": f"Bearer {admin_auth.json()['access_token']}"
    }

    updated_response = await client.patch(
        f"{settings.API_V1_STR}/bans/{ban.uuid}",
        headers=admin_headers,
        json={
            "ban_type": "other",
            "expires_at": "2026-05-20T00:00:00+00:00",
            "notes": "after",
        },
    )
    assert updated_response.status_code == 200
    assert updated_response.json()["ban_type"] == "other"
    assert updated_response.json()["expires_at"] == "2026-05-20T00:00:00Z"
    assert updated_response.json()["notes"] == "after"
    assert updated_response.json()["updated_by_steamid64"] == str(
        moderator_steamid64
    )
    assert updated_response.json()["updated_by_player"] == {
        "steamid64": str(moderator_steamid64),
        "display_name": "Patch Alias",
    }

    unban_response = await client.patch(
        f"{settings.API_V1_STR}/bans/{ban.uuid}",
        headers=admin_headers,
        json={
            "ban_type": "other",
            "expires_at": "2026-04-30T00:00:00+00:00",
            "notes": "manually unbanned",
        },
    )
    assert unban_response.status_code == 200
    assert unban_response.json()["expires_at"] == "2026-04-30T00:00:00Z"

    refreshed_ban = await db.get(Ban, ban.uuid)
    assert refreshed_ban is not None
    assert refreshed_ban.ban_type == BanType.OTHER
    assert refreshed_ban.notes == "manually unbanned"
    assert refreshed_ban.expires_at == datetime(2026, 4, 30, tzinfo=UTC)
    assert refreshed_ban.updated_by_steamid64 == moderator_steamid64


async def test_delete_ban_allows_superuser_for_bans_without_external_id(
    client: AsyncClient,
    db: AsyncSession,
    superuser_token_headers: dict[str, str],
) -> None:
    await _clear_bans(db)
    target_steamid64 = random_steamid64()
    await _create_player(db, steamid64=target_steamid64, name="Delete Target")
    ban = await _create_ban(
        db,
        id=None,
        ban_type=BanType.BHOP_MACRO,
        steamid64=target_steamid64,
        expires_at=None,
        player_name="Delete Target",
    )

    response = await client.delete(
        f"{settings.API_V1_STR}/bans/{ban.uuid}",
        headers=superuser_token_headers,
    )

    assert response.status_code == 200
    assert response.json() == {"message": "Ban deleted successfully"}
    assert await db.get(Ban, ban.uuid) is None


async def test_delete_ban_rejects_admin_and_mirrored_bans(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    await _clear_bans(db)
    target_steamid64 = random_steamid64()
    await _create_player(db, steamid64=target_steamid64, name="Delete Guard")
    mirrored_ban = await _create_ban(
        db,
        id=1202,
        ban_type=BanType.STRAFE_HACK,
        steamid64=target_steamid64,
        expires_at=None,
        player_name="Delete Guard",
    )
    admin_auth = await client.post(
        f"{settings.API_V1_STR}/private/auth/session",
        json={
            "steamid64": random_steamid64(),
            "roles": ["admin"],
            "is_active": True,
            "name": "Delete Admin",
        },
    )
    admin_headers = {
        "Authorization": f"Bearer {admin_auth.json()['access_token']}"
    }
    superuser_auth = await client.post(
        f"{settings.API_V1_STR}/private/auth/session",
        json={
            "steamid64": settings.SUPER_USER_STEAMID64,
            "roles": ["superuser"],
            "is_active": True,
            "name": "Delete Superuser",
        },
    )
    superuser_headers = {
        "Authorization": f"Bearer {superuser_auth.json()['access_token']}"
    }

    admin_response = await client.delete(
        f"{settings.API_V1_STR}/bans/{mirrored_ban.uuid}",
        headers=admin_headers,
    )
    assert admin_response.status_code == 403

    mirrored_response = await client.delete(
        f"{settings.API_V1_STR}/bans/{mirrored_ban.uuid}",
        headers=superuser_headers,
    )
    assert mirrored_response.status_code == 409
    assert mirrored_response.json() == {
        "detail": "Only bans without a GlobalAPI id can be deleted"
    }
    assert await db.get(Ban, mirrored_ban.uuid) is not None
