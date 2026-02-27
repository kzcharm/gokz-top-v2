from fastapi.encoders import jsonable_encoder
from sqlmodel import Session

from app import crud
from app.core.config import settings
from app.models import UserCreate, UserUpdate
from tests.utils.utils import random_steamid64


def test_create_user(db: Session) -> None:
    steamid64 = random_steamid64()
    user_in = UserCreate(steamid64=steamid64)

    user = crud.create_user(session=db, user_create=user_in)

    assert user.steamid64 == steamid64
    assert user.is_active is True
    assert user.is_superuser is False


def test_create_user_creates_player(db: Session) -> None:
    steamid64 = random_steamid64()
    user_in = UserCreate(steamid64=steamid64)

    crud.create_user(session=db, user_create=user_in)
    player = crud.get_player_by_steamid64(session=db, steamid64=steamid64)

    assert player is not None
    assert player.steamid64 == steamid64
    assert player.name


def test_get_user_by_steamid64(db: Session) -> None:
    steamid64 = random_steamid64()
    created = crud.get_or_create_user_from_steam(session=db, steamid64=steamid64)

    fetched = crud.get_user_by_steamid64(session=db, steamid64=steamid64)

    assert fetched is not None
    assert fetched.steamid64 == created.steamid64
    assert fetched.steamid64 == steamid64


def test_get_or_create_user_from_steam_is_idempotent(db: Session) -> None:
    steamid64 = random_steamid64()

    first = crud.get_or_create_user_from_steam(session=db, steamid64=steamid64)
    second = crud.get_or_create_user_from_steam(session=db, steamid64=steamid64)

    assert first.steamid64 == second.steamid64
    assert first.steamid64 == second.steamid64


def test_get_or_create_user_from_steam_sets_superuser_for_configured_id(
    db: Session,
) -> None:
    user = crud.get_or_create_user_from_steam(
        session=db,
        steamid64=settings.SUPER_USER_STEAMID64,
    )

    assert user.is_superuser is True


def test_get_or_create_user_from_steam_clears_superuser_for_non_configured_id(
    db: Session,
) -> None:
    steamid64 = random_steamid64()
    user = crud.get_or_create_user_from_steam(session=db, steamid64=steamid64)
    user.is_superuser = True
    db.add(user)
    db.commit()
    db.refresh(user)

    refreshed = crud.get_or_create_user_from_steam(session=db, steamid64=steamid64)

    assert refreshed.is_superuser is False


def test_update_user(db: Session) -> None:
    steamid64 = random_steamid64()
    user = crud.get_or_create_user_from_steam(session=db, steamid64=steamid64)

    update = UserUpdate(is_active=False, is_superuser=True)
    updated = crud.update_user(session=db, db_user=user, user_in=update)

    assert updated.is_active is False
    assert updated.is_superuser is True


def test_to_user_public_includes_player(db: Session) -> None:
    steamid64 = random_steamid64()
    user = crud.get_or_create_user_from_steam(session=db, steamid64=steamid64)

    user_public = crud.to_user_public(session=db, user=user)

    assert user_public.steamid64 == str(steamid64)
    assert user_public.player is not None
    assert user_public.player.steamid64 == str(steamid64)

    same_user = db.get(type(user), user.steamid64)
    assert same_user is not None
    assert (
        jsonable_encoder(user)["steamid64"] == jsonable_encoder(same_user)["steamid64"]
    )
