import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models import Jumpstat, JumpstatType, KZMode, Player
from app.services.jump_replay_retention import (
    cleanup_old_unkept_jump_replays_once,
    get_jump_replay_eligibility,
)
from app.services.jump_replay_storage import get_jump_replay_path, save_jump_replay
from tests.utils.server import create_server_group
from tests.utils.utils import random_steamid64

pytestmark = pytest.mark.asyncio


def _strafe_stats() -> list[dict[str, float | int]]:
    return [
        {
            "index": 1,
            "sync_percent": 80,
            "gain": 10.0,
            "loss": 0.0,
            "airtime_percent": 100,
            "width": 20.0,
            "overlap_count": 0,
            "dead_air_count": 0,
        }
    ]


async def _create_player(db: AsyncSession, *, steamid64: int) -> None:
    db.add(Player(steamid64=steamid64, name=str(steamid64)))
    await db.commit()


async def _create_jumpstat(
    db: AsyncSession,
    *,
    player_steamid64: int,
    server_group_id: uuid.UUID,
    mode: KZMode = KZMode.KZT,
    type: JumpstatType = JumpstatType.LJ,
    distance: str,
    jumped_at: datetime,
) -> Jumpstat:
    jumpstat = Jumpstat(
        player_steamid64=player_steamid64,
        server_group_id=server_group_id,
        mode=mode,
        type=type,
        distance=Decimal(distance),
        block=None,
        strafes=1,
        sync_percent=80,
        pre_speed=Decimal("276.0000"),
        max_speed=Decimal("350.0000"),
        w_count=0,
        overlap_count=0,
        dead_air_count=0,
        width=Decimal("20.0000"),
        height=Decimal("55.0000"),
        airtime_percent=100,
        offset=Decimal("0.0000"),
        crouched_ticks=0,
        edge=None,
        deviation=Decimal("0.0000"),
        strafe_stats=_strafe_stats(),
        jumped_at=jumped_at,
        created_at=jumped_at,
        updated_at=jumped_at,
    )
    db.add(jumpstat)
    await db.commit()
    await db.refresh(jumpstat)
    return jumpstat


async def test_jump_replay_eligibility_keeps_ten_ljs_and_one_other_type(
    db: AsyncSession,
) -> None:
    group, _api_key = await create_server_group(db, name="Retention Group")
    steamid64 = random_steamid64()
    await _create_player(db, steamid64=steamid64)
    for index in range(10):
        await _create_jumpstat(
            db,
            player_steamid64=steamid64,
            server_group_id=group.id,
            distance=str(300 - index),
            jumped_at=datetime(2026, 5, 1, 12, index, tzinfo=UTC),
        )
    await _create_jumpstat(
        db,
        player_steamid64=steamid64,
        server_group_id=group.id,
        type=JumpstatType.BH,
        distance="280.0000",
        jumped_at=datetime(2026, 5, 1, 13, 0, tzinfo=UTC),
    )

    lj = await get_jump_replay_eligibility(
        session=db,
        player_steamid64=steamid64,
        mode=KZMode.KZT,
        jump_type=JumpstatType.LJ,
        distance=Decimal("291.0000"),
    )
    bh = await get_jump_replay_eligibility(
        session=db,
        player_steamid64=steamid64,
        mode=KZMode.KZT,
        jump_type=JumpstatType.BH,
        distance=Decimal("279.0000"),
    )
    invalid = await get_jump_replay_eligibility(
        session=db,
        player_steamid64=steamid64,
        mode=KZMode.KZT,
        jump_type=JumpstatType.INV,
        distance=Decimal("999.0000"),
    )

    assert lj.eligible is True
    assert lj.keep_limit == 10
    assert lj.rank == 10
    assert bh.eligible is False
    assert bh.keep_limit == 1
    assert bh.rank == 2
    assert invalid.eligible is False
    assert invalid.keep_limit == 0


async def test_cleanup_deletes_only_old_replay_files_outside_keep_set(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(settings, "REPLAY_STORAGE_DIR", tmp_path)
    group, _api_key = await create_server_group(db, name="Cleanup Group")
    steamid64 = random_steamid64()
    await _create_player(db, steamid64=steamid64)
    now = datetime(2026, 5, 31, 12, 0, tzinfo=UTC)
    jumpstats: list[Jumpstat] = []
    for index in range(12):
        jumpstat = await _create_jumpstat(
            db,
            player_steamid64=steamid64,
            server_group_id=group.id,
            distance=str(300 - index),
            jumped_at=now - timedelta(days=10, minutes=index),
        )
        save_jump_replay(jumpstat_id=jumpstat.id, replay_bytes=f"lj-{index}".encode())
        jumpstats.append(jumpstat)
    recent_non_kept = await _create_jumpstat(
        db,
        player_steamid64=steamid64,
        server_group_id=group.id,
        distance="100.0000",
        jumped_at=now - timedelta(days=1),
    )
    save_jump_replay(jumpstat_id=recent_non_kept.id, replay_bytes=b"recent")

    result = await cleanup_old_unkept_jump_replays_once(session=db, now=now)

    assert result.checked == 2
    assert result.deleted == 2
    assert result.missing == 0
    assert result.errors == 0
    for jumpstat in jumpstats[:10]:
        assert get_jump_replay_path(jumpstat_id=jumpstat.id).exists()
    for jumpstat in jumpstats[10:]:
        assert not get_jump_replay_path(jumpstat_id=jumpstat.id).exists()
    assert get_jump_replay_path(jumpstat_id=recent_non_kept.id).exists()
