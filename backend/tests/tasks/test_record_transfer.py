from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import KZMode, Map, Player, Record, ServerGlobalapi
from app.tasks import record_transfer
from tests.utils.utils import random_steamid64

pytestmark = pytest.mark.asyncio


async def test_rebuild_target_player_record_dates_uses_all_target_records(
    db: AsyncSession,
) -> None:
    source_steamid64 = random_steamid64()
    target_steamid64 = random_steamid64()
    stale_source_created_at = datetime(2025, 1, 1, tzinfo=UTC)
    stale_source_last_played_at = datetime(2025, 2, 1, tzinfo=UTC)
    stale_target_created_at = datetime(2026, 1, 1, tzinfo=UTC)
    stale_target_last_played_at = datetime(2026, 2, 1, tzinfo=UTC)
    first_record_at = datetime(2024, 3, 1, tzinfo=UTC)
    last_record_at = datetime(2026, 3, 1, tzinfo=UTC)

    source_player = Player(
        steamid64=source_steamid64,
        name="Source",
        created_at=stale_source_created_at,
        last_played_at=stale_source_last_played_at,
    )
    target_player = Player(
        steamid64=target_steamid64,
        name="Target",
        created_at=stale_target_created_at,
        last_played_at=stale_target_last_played_at,
    )
    db.add_all([source_player, target_player])
    db.add(ServerGlobalapi(id=981_240, name="Record Transfer Test"))
    db.add(Map(id=981_241, name="kz_record_transfer_test"))
    await db.flush()
    db.add_all(
        [
            Record(
                id=9_812_400,
                steamid64=target_steamid64,
                server_id=981_240,
                mode=KZMode.KZT,
                map_id=981_241,
                time=Decimal("40.000"),
                created_at=first_record_at,
                updated_at=first_record_at,
            ),
            Record(
                id=9_812_401,
                steamid64=target_steamid64,
                server_id=981_240,
                mode=KZMode.KZT,
                map_id=981_241,
                time=Decimal("39.000"),
                created_at=last_record_at,
                updated_at=last_record_at,
            ),
        ]
    )
    await db.flush()

    await record_transfer._rebuild_target_player_record_dates(
        session=db,
        target_steamid64=target_steamid64,
    )
    await db.flush()

    assert target_player.created_at == first_record_at
    assert target_player.last_played_at == last_record_at
    assert source_player.created_at == stale_source_created_at
    assert source_player.last_played_at == stale_source_last_played_at
