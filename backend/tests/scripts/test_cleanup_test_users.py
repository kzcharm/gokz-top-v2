import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app import cleanup_test_users as cleanup_module
from app.cleanup_test_users import (
    cleanup_test_users,
    find_cleanup_candidates,
    format_cleanup_result,
)
from app.models import (
    Ban,
    BanType,
    LeaderboardPlayer,
    Map,
    ModeScope,
    Player,
    Record,
    ServerGlobalapi,
    User,
    UserRole,
)
from tests.utils.utils import random_steamid64

pytestmark = pytest.mark.asyncio


async def _create_test_user(
    db: AsyncSession,
    *,
    name: str = "Test User",
    roles: list[UserRole] | None = None,
) -> int:
    steamid64 = random_steamid64()
    db.add(Player(steamid64=steamid64, name=name))
    db.add(User(steamid64=steamid64, is_active=True, roles=roles or []))
    await db.commit()
    return steamid64


async def test_find_cleanup_candidates_only_selects_disposable_test_users(
    db: AsyncSession,
) -> None:
    disposable = await _create_test_user(db)
    named_differently = await _create_test_user(db, name="Real User")
    referenced = await _create_test_user(db)
    superuser = await _create_test_user(db, roles=[UserRole.SUPERUSER])
    map_id = 1_500_000_000 + (random_steamid64() % 1_000_000)
    server_id = 1_600_000_000 + (random_steamid64() % 1_000_000)
    record_id = 1_700_000_000 + (random_steamid64() % 1_000_000)

    db.add(Map(id=map_id, name=f"kz_testmap_{map_id}"))
    db.add(
        ServerGlobalapi(
            id=server_id,
            ip="127.0.0.1",
            port=27015,
            owner_steamid64=None,
        )
    )
    await db.commit()
    db.add(
        Record(
            id=record_id,
            steamid64=referenced,
            server_id=server_id,
            mode_id=200,
            map_id=map_id,
            stage=0,
            time=1,
            teleports=0,
            points=0,
        )
    )
    await db.commit()

    steamid64s = await find_cleanup_candidates(session=db)

    assert disposable in steamid64s
    assert named_differently not in steamid64s
    assert referenced not in steamid64s
    assert superuser not in steamid64s


async def test_cleanup_test_users_dry_run_reports_without_deleting(
    db: AsyncSession,
) -> None:
    disposable = await _create_test_user(db)

    result = await cleanup_test_users(session=db, dry_run=True)

    assert result.dry_run is True
    assert result.deleted_count == 0
    assert disposable in result.steamid64s
    assert await db.get(User, disposable) is not None
    assert await db.get(Player, disposable) is not None

    output = format_cleanup_result(result)
    assert "DRY RUN" in output
    assert str(disposable) in output


async def test_cleanup_test_users_delete_removes_only_safe_candidates(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    disposable = await _create_test_user(db)
    protected = await _create_test_user(db)

    db.add(
        LeaderboardPlayer(
            scope=ModeScope.OVR,
            steamid64=protected,
            rating=1,
        )
    )
    await db.commit()

    async def _fake_find_cleanup_candidates(*, session: AsyncSession) -> list[int]:
        del session
        return [disposable]

    monkeypatch.setattr(
        cleanup_module,
        "find_cleanup_candidates",
        _fake_find_cleanup_candidates,
    )

    result = await cleanup_test_users(session=db, dry_run=False)

    assert result.dry_run is False
    assert disposable in result.steamid64s
    assert await db.get(User, disposable) is None
    assert await db.get(Player, disposable) is None
    assert await db.get(User, protected) is not None
    assert await db.get(Player, protected) is not None


async def test_cleanup_test_users_skips_when_no_candidates(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_find_cleanup_candidates(*, session: AsyncSession) -> list[int]:
        del session
        return []

    monkeypatch.setattr(
        cleanup_module,
        "find_cleanup_candidates",
        _fake_find_cleanup_candidates,
    )

    result = await cleanup_test_users(session=db, dry_run=False)

    assert result.deleted_count == 0
    assert result.steamid64s == []


async def test_find_cleanup_candidates_includes_orphan_players(
    db: AsyncSession,
) -> None:
    steamid64 = random_steamid64()
    db.add(Player(steamid64=steamid64, name="Test User"))
    await db.commit()

    steamid64s = await find_cleanup_candidates(session=db)

    assert steamid64 in steamid64s


async def test_find_cleanup_candidates_excludes_players_referenced_by_bans(
    db: AsyncSession,
) -> None:
    steamid64 = random_steamid64()
    db.add(Player(steamid64=steamid64, name="Test User"))
    await db.flush()
    db.add(
        Ban(
            id=1_900_000_000 + (random_steamid64() % 1_000_000),
            ban_type=BanType.BHOP_HACK,
            steamid64=steamid64,
            notes="ban",
            stats="stats",
            server_id=1,
            updated_by_id="1",
        )
    )
    await db.commit()

    steamid64s = await find_cleanup_candidates(session=db)

    assert steamid64 not in steamid64s
