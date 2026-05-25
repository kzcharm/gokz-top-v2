from datetime import UTC, datetime

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.models import Player
from tests.utils.utils import random_steamid64


async def _create_player(
    *,
    db: AsyncSession,
    steamid64: int,
    name: str,
) -> Player:
    player = Player(steamid64=steamid64, name=name)
    db.add(player)
    await db.commit()
    await db.refresh(player)
    return player


@pytest.mark.asyncio
async def test_create_player_like_is_idempotent_per_utc_day(
    db: AsyncSession,
) -> None:
    viewer = await crud.get_or_create_user_from_steam(
        session=db,
        steamid64=random_steamid64(),
    )
    target = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Liked Player",
    )
    now = datetime(2026, 4, 4, 12, 0, tzinfo=UTC)

    await crud.create_player_like(
        session=db,
        viewer_steamid64=viewer.steamid64,
        target_steamid64=target.steamid64,
        now=now,
    )
    await crud.create_player_like(
        session=db,
        viewer_steamid64=viewer.steamid64,
        target_steamid64=target.steamid64,
        now=now.replace(hour=18),
    )

    assert (
        await crud.count_player_likes(
            session=db,
            target_steamid64=target.steamid64,
        )
        == 1
    )


@pytest.mark.asyncio
async def test_create_player_like_counts_unique_viewer_days(
    db: AsyncSession,
) -> None:
    viewer = await crud.get_or_create_user_from_steam(
        session=db,
        steamid64=random_steamid64(),
    )
    another_viewer = await crud.get_or_create_user_from_steam(
        session=db,
        steamid64=random_steamid64(),
    )
    target = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Popular Player",
    )

    await crud.create_player_like(
        session=db,
        viewer_steamid64=viewer.steamid64,
        target_steamid64=target.steamid64,
        now=datetime(2026, 4, 4, 23, 59, tzinfo=UTC),
    )
    await crud.create_player_like(
        session=db,
        viewer_steamid64=viewer.steamid64,
        target_steamid64=target.steamid64,
        now=datetime(2026, 4, 5, 0, 0, tzinfo=UTC),
    )
    await crud.create_player_like(
        session=db,
        viewer_steamid64=another_viewer.steamid64,
        target_steamid64=target.steamid64,
        now=datetime(2026, 4, 5, 9, 30, tzinfo=UTC),
    )

    assert (
        await crud.count_player_likes(
            session=db,
            target_steamid64=target.steamid64,
        )
        == 3
    )


@pytest.mark.asyncio
async def test_create_player_like_ignores_self_likes(db: AsyncSession) -> None:
    viewer = await crud.get_or_create_user_from_steam(
        session=db,
        steamid64=random_steamid64(),
    )

    await crud.create_player_like(
        session=db,
        viewer_steamid64=viewer.steamid64,
        target_steamid64=viewer.steamid64,
        now=datetime(2026, 4, 4, 12, 0, tzinfo=UTC),
    )

    assert (
        await crud.count_player_likes(
            session=db,
            target_steamid64=viewer.steamid64,
        )
        == 0
    )
