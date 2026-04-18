import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.core.config import settings
from app.models import Mode


@pytest.mark.asyncio
async def test_read_modes_public_returns_seeded_modes(client: AsyncClient) -> None:
    response = await client.get(f"{settings.API_V1_STR}/modes/")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 4
    assert [mode["id"] for mode in payload] == [200, 201, 202, 203]

    expected = {
        200: ("kz_timer", "KZT", 2),
        201: ("kz_simple", "SKZ", 1),
        202: ("kz_vanilla", "VNL", 0),
        203: ("kz_noperfkz", "NKZ", 3),
    }
    for mode in payload:
        name, short_name, id_plugin = expected[mode["id"]]
        assert mode["name"] == name
        assert mode["name_short"] == short_name
        assert mode["id_plugin"] == id_plugin
        assert mode["supported_tickrates"] is None
        assert isinstance(mode["contact_steamid64"], str)
        assert isinstance(mode["updated_by_id"], str)


@pytest.mark.asyncio
async def test_read_modes_v0_contract(client: AsyncClient) -> None:
    response = await client.get("/v0/modes")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 4
    assert [mode["id"] for mode in payload] == [200, 201, 202, 203]

    mode = payload[0]
    assert mode["name"] == "kz_timer"
    assert isinstance(mode["latest_version"], int)
    assert isinstance(mode["latest_version_description"], str)
    assert mode["supported_tickrates"] is None
    assert isinstance(mode["contact_steamid64"], int)
    assert isinstance(mode["updated_by_id"], int)
    assert "name_short" not in mode
    assert "id_plugin" not in mode


@pytest.mark.asyncio
async def test_get_mode_by_id_and_name(client: AsyncClient) -> None:
    by_id_response = await client.get(f"{settings.API_V1_STR}/modes/id/201")
    by_name_response = await client.get(f"{settings.API_V1_STR}/modes/name/kz_simple")

    assert by_id_response.status_code == 200
    assert by_name_response.status_code == 200
    assert by_id_response.json()["id"] == 201
    assert by_id_response.json()["name"] == "kz_simple"
    assert by_name_response.json()["id"] == 201
    assert by_name_response.json()["name_short"] == "SKZ"


@pytest.mark.asyncio
async def test_get_mode_v0_by_id_and_name(client: AsyncClient) -> None:
    by_id_response = await client.get("/v0/modes/id/201")
    by_name_response = await client.get("/v0/modes/name/kz_simple")

    assert by_id_response.status_code == 200
    assert by_name_response.status_code == 200
    assert by_id_response.json()["id"] == 201
    assert by_id_response.json()["name"] == "kz_simple"
    assert by_name_response.json()["id"] == 201
    assert by_name_response.json()["name"] == "kz_simple"
    assert "name_short" not in by_name_response.json()


@pytest.mark.asyncio
async def test_get_mode_not_found(client: AsyncClient) -> None:
    by_id_response = await client.get(f"{settings.API_V1_STR}/modes/id/999")
    by_name_response = await client.get(
        f"{settings.API_V1_STR}/modes/name/unknown_mode"
    )

    assert by_id_response.status_code == 404
    assert by_name_response.status_code == 404
    assert by_id_response.json() == {"detail": "Mode not found"}
    assert by_name_response.json() == {"detail": "Mode not found"}


@pytest.mark.asyncio
async def test_get_mode_v0_not_found(client: AsyncClient) -> None:
    by_id_response = await client.get("/v0/modes/id/999")
    by_name_response = await client.get("/v0/modes/name/unknown_mode")

    assert by_id_response.status_code == 404
    assert by_name_response.status_code == 404
    assert by_id_response.json() == {"detail": "Mode not found"}
    assert by_name_response.json() == {"detail": "Mode not found"}


@pytest.mark.asyncio
async def test_update_mode_requires_authentication(client: AsyncClient) -> None:
    response = await client.put(
        f"{settings.API_V1_STR}/admin/modes/200",
        json={"latest_version": 9999},
    )

    assert response.status_code in {401, 403}


@pytest.mark.asyncio
async def test_update_mode_requires_superuser(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    response = await client.put(
        f"{settings.API_V1_STR}/admin/modes/200",
        headers=normal_user_token_headers,
        json={"latest_version": 9999},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "The user doesn't have enough privileges"}


@pytest.mark.asyncio
async def test_update_mode_superuser_updates_metadata(
    client: AsyncClient,
    superuser_token_headers: dict[str, str],
) -> None:
    response = await client.put(
        f"{settings.API_V1_STR}/admin/modes/200",
        headers=superuser_token_headers,
        json={
            "description": "Updated metadata description",
            "latest_version": 2200,
            "latest_version_description": "1.200",
            "website": "forum.gokz.org",
            "repo": "https://github.com/KZGlobalTeam/gokz",
            "contact_steamid64": "76561198165203332",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == 200
    assert payload["name"] == "kz_timer"
    assert payload["name_short"] == "KZT"
    assert payload["id_plugin"] == 2
    assert payload["description"] == "Updated metadata description"
    assert payload["latest_version"] == 2200
    assert payload["latest_version_description"] == "1.200"
    assert payload["repo"] == "https://github.com/KZGlobalTeam/gokz"
    assert payload["contact_steamid64"] == "76561198165203332"
    assert payload["updated_by_id"] == str(settings.SUPER_USER_STEAMID64)


@pytest.mark.asyncio
async def test_update_mode_rejects_extra_fields(
    client: AsyncClient,
    superuser_token_headers: dict[str, str],
) -> None:
    response = await client.put(
        f"{settings.API_V1_STR}/admin/modes/200",
        headers=superuser_token_headers,
        json={"name": "kz_hacked"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_sync_canonical_modes_restores_canonical_keys(
    db: AsyncSession,
) -> None:
    mode = await db.get(Mode, 200)
    assert mode is not None

    mode.name = "drifted_mode_name"
    mode.id_plugin = 99
    mode.description = "Custom metadata survives sync"
    db.add(mode)
    await db.commit()

    await crud.sync_canonical_modes(session=db)

    db.expire_all()
    refreshed_mode = await db.get(Mode, 200)
    assert refreshed_mode is not None
    assert refreshed_mode.name == "kz_timer"
    assert refreshed_mode.name_short == "KZT"
    assert refreshed_mode.id_plugin == 2
    assert refreshed_mode.description == "Custom metadata survives sync"
