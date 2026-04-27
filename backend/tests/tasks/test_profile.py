from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import update
from sqlmodel.ext.asyncio.session import AsyncSession
from typer.testing import CliRunner

from app import cli
from app.crud import player as player_crud
from app.models import LeaderboardPlayer, ModeScope, Player
from app.tasks.build import profile
from tests.utils.utils import random_steamid64

pytestmark = pytest.mark.asyncio


class _BoundSessionFactory:
    def __init__(self, session: AsyncSession) -> None:
        bind = session.bind
        if bind is None:
            raise AssertionError("AsyncSession is not bound to a connection")
        self._bind = bind

    def __call__(self) -> _BoundSessionContext:
        return _BoundSessionContext(self._bind)


class _BoundSessionContext:
    def __init__(self, bind: Any) -> None:
        self._bind = bind
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> AsyncSession:
        self._session = AsyncSession(
            bind=self._bind,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        return self._session

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None:
        del exc_type, exc, tb
        if self._session is not None:
            await self._session.close()


class _DummyProgress:
    def __init__(self, *, total: int | None = None) -> None:
        self.total = total
        self.count = 0

    def set_postfix_str(self, value: str) -> None:
        del value

    def update(self, amount: int) -> None:
        self.count += amount

    def close(self) -> None:
        return None


def _dummy_tqdm_factory() -> Callable[..., _DummyProgress]:
    def _dummy_tqdm(*args: Any, **kwargs: Any) -> _DummyProgress:
        del args
        return _DummyProgress(total=kwargs.get("total"))

    return _dummy_tqdm


async def test_create_or_update_player_from_steam_if_fetched_skips_insert_when_fetch_fails(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    steamid64 = random_steamid64()

    async def _fake_fetch_player_from_steam_api(
        _steamid64: int,
    ) -> dict[str, str | bool | None]:
        return {
            "name": str(_steamid64),
            "custom_id": None,
            "avatar_hash": None,
            "country": None,
            "fetched": False,
        }

    monkeypatch.setattr(
        player_crud,
        "_fetch_player_from_steam_api",
        _fake_fetch_player_from_steam_api,
    )

    (
        player,
        was_created,
    ) = await player_crud.create_or_update_player_from_steam_if_fetched(
        session=db,
        steamid64=steamid64,
    )

    assert player is None
    assert was_created is False
    assert await db.get(Player, steamid64) is None


async def test_rebuild_player_profiles_can_create_missing_player_for_explicit_steamid(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target_steamid64 = random_steamid64()

    async def _fake_fetch_players_from_steam_api(
        steamid64s: list[int],
    ) -> dict[int, dict[str, str | bool | None]]:
        assert steamid64s == [target_steamid64]
        return {
            target_steamid64: {
                "name": "Created From Steam",
                "custom_id": "Created_From_Steam",
                "avatar_hash": "d" * 40,
                "country": "SE",
                "fetched": True,
            }
        }

    monkeypatch.setattr(
        "app.tasks.build.profile.crud._fetch_players_from_steam_api",
        _fake_fetch_players_from_steam_api,
    )
    monkeypatch.setattr(
        profile,
        "async_session_maker",
        _BoundSessionFactory(db),
    )
    monkeypatch.setattr(
        profile,
        "_get_tqdm",
        _dummy_tqdm_factory,
    )

    result = await profile.rebuild_player_profiles(steamid64s=[target_steamid64])

    assert result.selected == 1
    assert result.created == 1
    assert result.updated == 0
    assert result.skipped == 0

    created_player = await db.get(Player, target_steamid64)
    assert created_player is not None
    assert created_player.name == "Created From Steam"
    assert created_player.custom_id == "created_from_steam"
    assert created_player.avatar_hash == "d" * 40
    assert created_player.country == "SE"


async def test_load_target_steamid64s_supports_leaderboard_scope_ordering(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_player = random_steamid64()
    second_player = random_steamid64()
    third_player = random_steamid64()

    db.add(Player(steamid64=first_player, name="First", avatar_hash="a" * 40))
    db.add(Player(steamid64=second_player, name="Second", avatar_hash="b" * 40))
    db.add(Player(steamid64=third_player, name="Third", avatar_hash=None))
    await db.commit()

    db.add(
        LeaderboardPlayer(
            scope=ModeScope.OVR,
            steamid64=second_player,
            rating=2_147_483_646,
        )
    )
    db.add(
        LeaderboardPlayer(
            scope=ModeScope.OVR,
            steamid64=first_player,
            rating=2_147_483_647,
        )
    )
    db.add(
        LeaderboardPlayer(
            scope=ModeScope.OVR,
            steamid64=third_player,
            rating=0,
        )
    )
    await db.commit()

    monkeypatch.setattr(
        profile,
        "async_session_maker",
        _BoundSessionFactory(db),
    )

    selected = await profile.load_target_steamid64s(leaderboard_scope=ModeScope.OVR)

    assert selected[:2] == [first_player, second_player]
    assert third_player not in selected


async def test_rebuild_player_profiles_fetches_steam_profiles_in_batches_of_four(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    steamid64s = [random_steamid64() for _ in range(5)]
    batch_calls: list[list[int]] = []
    upsert_calls: list[int] = []

    async def _fake_fetch_players_from_steam_api(
        batch: list[int],
    ) -> dict[int, dict[str, str | bool | None]]:
        batch_calls.append(list(batch))
        return {
            steamid64: {
                "name": f"Player {index}",
                "custom_id": f"player_{index}",
                "avatar_hash": "a" * 40,
                "country": "DE",
                "fetched": True,
            }
            for index, steamid64 in enumerate(batch, start=1)
        }

    async def _fake_upsert(
        *,
        session: AsyncSession,
        steamid64: int,
        steam_data: dict[str, str | bool | None] | None,
    ) -> tuple[object | None, bool]:
        del session
        assert steam_data is not None
        upsert_calls.append(steamid64)
        return object(), False

    monkeypatch.setattr(
        profile,
        "async_session_maker",
        _BoundSessionFactory(db),
    )
    monkeypatch.setattr(
        profile,
        "_get_tqdm",
        _dummy_tqdm_factory,
    )
    monkeypatch.setattr(
        "app.tasks.build.profile.crud._fetch_players_from_steam_api",
        _fake_fetch_players_from_steam_api,
    )
    monkeypatch.setattr(
        "app.tasks.build.profile.crud.create_or_update_player_from_steam_data_if_fetched",
        _fake_upsert,
    )

    result = await profile.rebuild_player_profiles(steamid64s=steamid64s)

    assert result.selected == 5
    assert result.created == 0
    assert result.updated == 5
    assert result.skipped == 0
    assert batch_calls == [steamid64s[:4], steamid64s[4:]]
    assert upsert_calls == steamid64s


def test_cli_profile_help() -> None:
    runner = CliRunner()

    result = runner.invoke(cli.app, ["sync", "profiles", "--help"])

    assert result.exit_code == 0
    assert "Select only players that do" in result.output
    assert "not have an avatar hash yet." in result.output


async def test_load_target_steamid64s_supports_stale_days_selection(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fresh_player = random_steamid64()
    stale_player = random_steamid64()
    null_updated_player = random_steamid64()
    now = datetime(2026, 4, 13, tzinfo=UTC)

    db.add(
        Player(
            steamid64=fresh_player,
            name="Fresh",
            updated_at=now - timedelta(days=10),
        )
    )
    db.add(
        Player(
            steamid64=stale_player,
            name="Stale",
            updated_at=now - timedelta(days=31),
        )
    )
    db.add(
        Player(
            steamid64=null_updated_player,
            name="Never Synced",
            updated_at=None,
        )
    )
    await db.commit()
    await db.exec(
        update(Player)
        .where(Player.steamid64 == null_updated_player)
        .values(updated_at=None)
    )
    await db.commit()

    monkeypatch.setattr(
        profile,
        "async_session_maker",
        _BoundSessionFactory(db),
    )

    selected = await profile.load_target_steamid64s(
        only_missing_avatar=False,
        stale_before=now - timedelta(days=30),
    )

    assert fresh_player not in selected
    assert stale_player in selected
    assert null_updated_player in selected
