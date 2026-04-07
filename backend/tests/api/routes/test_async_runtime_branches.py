from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch
from urllib.parse import urlencode
from uuid import uuid4

import jwt
import pytest
from fastapi import HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.requests import Request

from app import crud
from app.api import deps
from app.api.v1 import admin_modes as admin_modes_routes
from app.api.v1 import login as login_routes
from app.api.v1 import modes as modes_routes
from app.api.v1 import players as players_routes
from app.api.v1 import private as private_routes
from app.api.v1 import users as users_routes
from app.api.v1 import utils as utils_routes
from app.api.v1.private import PrivateAuthSessionCreate
from app.core import security
from app.core.config import settings
from app.models import (
    ModeAdminUpdate,
    Player,
    PlayersBatchRead,
    PlayersListQuery,
    PlayerUpdate,
    User,
    UserUpdate,
)
from tests.utils.utils import random_steamid64


def _build_request(path: str, params: dict[str, str]) -> Request:
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": urlencode(params).encode(),
        "headers": [],
        "client": ("testclient", 12345),
        "server": ("testserver", 80),
    }

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(scope, receive=receive)


async def _create_user(
    db: AsyncSession,
    *,
    superuser: bool = False,
    active: bool = True,
) -> User:
    user = await crud.get_or_create_user_from_steam(
        session=db, steamid64=random_steamid64()
    )
    user.is_superuser = superuser
    user.is_active = active
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.mark.asyncio
async def test_users_routes_direct_branches(db: AsyncSession) -> None:
    superuser = await _create_user(db, superuser=True)
    normal_user = await _create_user(db)
    other_user = await _create_user(db)

    users = await users_routes.read_users(session=db)
    assert users.count >= 1
    assert users.data

    me = await users_routes.read_user_me(current_user=normal_user, session=db)
    assert me.steamid64 == str(normal_user.steamid64)
    assert me.last_visited_at is not None

    mine = await users_routes.read_user_by_id(
        user_id=str(normal_user.steamid64),
        session=db,
        current_user=normal_user,
    )
    assert mine.steamid64 == str(normal_user.steamid64)

    with pytest.raises(HTTPException, match="enough privileges"):
        await users_routes.read_user_by_id(
            user_id=str(other_user.steamid64),
            session=db,
            current_user=normal_user,
        )

    with pytest.raises(HTTPException, match="User not found"):
        await users_routes.read_user_by_id(
            user_id=str(random_steamid64()),
            session=db,
            current_user=superuser,
        )

    found = await users_routes.read_user_by_id(
        user_id=str(other_user.steamid64),
        session=db,
        current_user=superuser,
    )
    assert found.steamid64 == str(other_user.steamid64)

    with pytest.raises(HTTPException, match="does not exist"):
        await users_routes.update_user(
            session=db,
            user_id=str(random_steamid64()),
            user_in=UserUpdate(is_active=True),
        )

    changed = await users_routes.update_user(
        session=db,
        user_id=str(other_user.steamid64),
        user_in=UserUpdate(is_active=False),
    )
    assert changed.is_active is False

    with pytest.raises(HTTPException, match="Invalid steamid64"):
        await users_routes.read_user_by_id(
            user_id="not-a-number",
            session=db,
            current_user=superuser,
        )

    with pytest.raises(HTTPException, match="User not found"):
        await users_routes.delete_user(
            session=db,
            current_user=superuser,
            user_id=str(random_steamid64()),
        )

    with pytest.raises(HTTPException, match="delete themselves"):
        await users_routes.delete_user(
            session=db,
            current_user=superuser,
            user_id=str(superuser.steamid64),
        )

    target_for_delete = await _create_user(db)
    deleted = await users_routes.delete_user(
        session=db,
        current_user=superuser,
        user_id=str(target_for_delete.steamid64),
    )
    assert deleted.message == "User deleted successfully"


@pytest.mark.asyncio
async def test_players_routes_direct_branches(db: AsyncSession) -> None:
    future_time = datetime.now(UTC) + timedelta(days=2)
    existing = Player(
        steamid64=random_steamid64(),
        name="Existing Player",
        created_at=future_time,
        updated_at=future_time,
    )
    db.add(existing)
    await db.commit()
    await db.refresh(existing)

    listing = await players_routes.read_players(
        session=db,
        query=PlayersListQuery(offset=0, limit=10),
    )
    assert listing.count >= 1
    assert any(player.steamid64 == str(existing.steamid64) for player in listing.data)

    batch = await players_routes.read_players_batch(
        session=db,
        body=PlayersBatchRead(
            steamid64s=[
                str(existing.steamid64),
                str(random_steamid64()),
                str(existing.steamid64),
            ]
        ),
    )
    assert batch.count == 3
    assert batch.data[0] is not None
    assert batch.data[1] is None
    assert batch.data[2] is not None

    updated = await players_routes.update_player(
        session=db,
        steamid64=str(existing.steamid64),
        player_in=PlayerUpdate(alias="Alias", country="DE"),
        current_user=User(
            steamid64=random_steamid64(),
            is_active=True,
            is_superuser=True,
        ),
    )
    assert updated.alias == "Alias"
    assert updated.country == "DE"

    with pytest.raises(HTTPException, match="Player not found"):
        await players_routes.update_player(
            session=db,
            steamid64=str(random_steamid64()),
            player_in=PlayerUpdate(alias="Missing"),
            current_user=User(
                steamid64=random_steamid64(),
                is_active=True,
                is_superuser=True,
            ),
        )

    with pytest.raises(HTTPException, match="Invalid steamid64"):
        await players_routes.update_player(
            session=db,
            steamid64="not-a-number",
            player_in=PlayerUpdate(alias="Invalid"),
            current_user=User(
                steamid64=random_steamid64(),
                is_active=True,
                is_superuser=True,
            ),
        )

    mocked_upsert = Player(steamid64=random_steamid64(), name="Upserted Player")
    with patch(
        "app.api.v1.players.crud.create_or_update_player_from_steam_if_fetched",
        new=AsyncMock(return_value=(mocked_upsert, False)),
    ):
        upserted = await players_routes.upsert_player_from_steam(
            session=db,
            steamid64=str(mocked_upsert.steamid64),
        )
    assert upserted.steamid64 == str(mocked_upsert.steamid64)


@pytest.mark.asyncio
async def test_modes_routes_direct_branches(db: AsyncSession) -> None:
    modes = await modes_routes.read_modes(session=db)
    assert len(modes) >= 4

    by_id = await modes_routes.read_mode_by_id(session=db, id=200)
    by_name = await modes_routes.read_mode_by_name(session=db, mode_name="kz_timer")
    assert by_id.id == 200
    assert by_name.name == "kz_timer"

    with pytest.raises(HTTPException, match="Mode not found"):
        await modes_routes.read_mode_by_id(session=db, id=9999)

    with pytest.raises(HTTPException, match="Mode not found"):
        await modes_routes.read_mode_by_name(session=db, mode_name="missing_mode")

    superuser = await _create_user(db, superuser=True)
    updated = await admin_modes_routes.update_mode(
        session=db,
        id=200,
        mode_in=ModeAdminUpdate(description="Direct route mode update"),
        current_user=superuser,
    )
    assert updated.description == "Direct route mode update"

    with pytest.raises(HTTPException, match="Invalid steamid64"):
        await admin_modes_routes.update_mode(
            session=db,
            id=200,
            mode_in=ModeAdminUpdate(contact_steamid64="not-a-number"),
            current_user=superuser,
        )

    with pytest.raises(HTTPException, match="Mode not found"):
        await admin_modes_routes.update_mode(
            session=db,
            id=9999,
            mode_in=ModeAdminUpdate(description="No mode"),
            current_user=superuser,
        )


@pytest.mark.asyncio
async def test_private_route_direct_branches(db: AsyncSession) -> None:
    body = PrivateAuthSessionCreate(
        steamid64=random_steamid64(),
        is_superuser=True,
        is_active=True,
        name="Route Test Name",
    )
    token = await private_routes.create_auth_session(body=body, session=db)
    assert token.access_token
    assert token.token_type == "bearer"

    user = await crud.get_user_by_steamid64(session=db, steamid64=body.steamid64)
    assert user is not None
    player = await crud.get_player_by_steamid64(session=db, steamid64=body.steamid64)
    assert player is not None
    assert player.name == "Route Test Name"


@pytest.mark.asyncio
async def test_deps_direct_branches(db: AsyncSession) -> None:
    with pytest.raises(HTTPException, match="Could not validate credentials"):
        await deps.get_current_user(session=db, token="bad-token")

    no_sub_token = jwt.encode(
        {"exp": datetime.now(UTC) + timedelta(minutes=5)},
        settings.SECRET_KEY,
        algorithm=security.ALGORITHM,
    )
    with pytest.raises(HTTPException, match="Could not validate credentials"):
        await deps.get_current_user(session=db, token=no_sub_token)

    non_int_sub_token = security.create_access_token(
        "abc",
        expires_delta=timedelta(minutes=5),
    )
    with pytest.raises(HTTPException, match="Could not validate credentials"):
        await deps.get_current_user(session=db, token=non_int_sub_token)

    missing_user_token = security.create_access_token(
        str(random_steamid64()),
        expires_delta=timedelta(minutes=5),
    )
    recreated = await deps.get_current_user(session=db, token=missing_user_token)
    assert recreated.steamid64 == int(jwt.decode(missing_user_token, options={"verify_signature": False})["sub"])

    with patch.object(settings, "ENVIRONMENT", "production"):
        missing_user_token = security.create_access_token(
            str(random_steamid64()),
            expires_delta=timedelta(minutes=5),
        )
        with pytest.raises(HTTPException, match="User not found"):
            await deps.get_current_user(session=db, token=missing_user_token)

    inactive_user = await _create_user(db, active=False)
    inactive_token = security.create_access_token(
        str(inactive_user.steamid64),
        expires_delta=timedelta(minutes=5),
    )
    with pytest.raises(HTTPException, match="Inactive user"):
        await deps.get_current_user(session=db, token=inactive_token)

    non_super = await _create_user(db, superuser=False)
    with pytest.raises(HTTPException, match="enough privileges"):
        deps.get_current_active_superuser(non_super)

    yes_super = await _create_user(db, superuser=True)
    assert deps.get_current_active_superuser(yes_super).is_superuser is True


@pytest.mark.asyncio
async def test_login_route_direct_branches(db: AsyncSession) -> None:
    steamid64 = random_steamid64()
    callback_request = _build_request(
        f"{settings.API_V1_STR}/login/steam/callback",
        {
            "openid.ns": "http://specs.openid.net/auth/2.0",
            "openid.mode": "id_res",
            "openid.op_endpoint": "https://steamcommunity.com/openid/login",
            "openid.claimed_id": f"https://steamcommunity.com/openid/id/{steamid64}",
            "openid.identity": f"https://steamcommunity.com/openid/id/{steamid64}",
            "openid.return_to": f"http://testserver{settings.API_V1_STR}/login/steam/callback",
            "openid.response_nonce": "2026-02-27T00:00:00Zabcdef",
            "openid.assoc_handle": "1234567890",
            "openid.signed": "op_endpoint,claimed_id,identity,return_to,response_nonce,assoc_handle",
            "openid.sig": "fake-signature",
        },
    )

    with patch(
        "app.api.v1.login.httpx.AsyncClient.post",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        with pytest.raises(HTTPException, match="Failed to verify OpenID response"):
            await login_routes.steam_callback(request=callback_request, session=db)

    mocked_response = Mock()
    mocked_response.raise_for_status.return_value = None
    mocked_response.text = "ns:http://specs.openid.net/auth/2.0\nis_valid:true"

    inactive = User(steamid64=steamid64, is_active=False, is_superuser=False)
    with (
        patch(
            "app.api.v1.login.httpx.AsyncClient.post",
            new=AsyncMock(return_value=mocked_response),
        ),
        patch(
            "app.api.v1.login.crud.get_or_create_user_from_steam",
            new=AsyncMock(return_value=inactive),
        ),
    ):
        with pytest.raises(HTTPException, match="Inactive user"):
            await login_routes.steam_callback(request=callback_request, session=db)

    active = User(steamid64=steamid64, is_active=True, is_superuser=False)
    with (
        patch(
            "app.api.v1.login.httpx.AsyncClient.post",
            new=AsyncMock(return_value=mocked_response),
        ),
        patch(
            "app.api.v1.login.crud.get_or_create_user_from_steam",
            new=AsyncMock(return_value=active),
        ),
    ):
        redirect = await login_routes.steam_callback(
            request=callback_request, session=db
        )
        assert redirect.headers["location"].startswith(
            f"{settings.FRONTEND_HOST.rstrip('/')}/auth/callback#access_token="
        )


@pytest.mark.asyncio
async def test_utils_route_direct() -> None:
    assert await utils_routes.health_check() is True
