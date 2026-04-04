from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.models import Player, PlayerFollow, User
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
async def test_create_player_follow_is_idempotent(db: AsyncSession) -> None:
    follower = await crud.get_or_create_user_from_steam(
        session=db,
        steamid64=random_steamid64(),
    )
    target = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Target Player",
    )

    first = await crud.create_player_follow(
        session=db,
        follower_steamid64=follower.steamid64,
        followed_steamid64=target.steamid64,
    )
    second = await crud.create_player_follow(
        session=db,
        follower_steamid64=follower.steamid64,
        followed_steamid64=target.steamid64,
    )

    assert first.follower_steamid64 == follower.steamid64
    assert first.followed_steamid64 == target.steamid64
    assert second.follower_steamid64 == follower.steamid64
    assert second.followed_steamid64 == target.steamid64

    followers, follower_count = await crud.get_player_followers(
        session=db,
        target_steamid64=target.steamid64,
        offset=0,
        limit=10,
    )
    assert follower_count == 1
    assert [player.steamid64 for player in followers] == [follower.steamid64]


@pytest.mark.asyncio
async def test_delete_player_follow_is_idempotent(db: AsyncSession) -> None:
    follower = await crud.get_or_create_user_from_steam(
        session=db,
        steamid64=random_steamid64(),
    )
    target = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Delete Target",
    )

    await crud.create_player_follow(
        session=db,
        follower_steamid64=follower.steamid64,
        followed_steamid64=target.steamid64,
    )

    deleted = await crud.delete_player_follow(
        session=db,
        follower_steamid64=follower.steamid64,
        followed_steamid64=target.steamid64,
    )
    deleted_again = await crud.delete_player_follow(
        session=db,
        follower_steamid64=follower.steamid64,
        followed_steamid64=target.steamid64,
    )

    assert deleted is True
    assert deleted_again is False
    assert (
        await crud.is_player_following(
            session=db,
            follower_steamid64=follower.steamid64,
            followed_steamid64=target.steamid64,
        )
        is False
    )


@pytest.mark.asyncio
async def test_get_player_follow_summary_counts_and_viewer_state(
    db: AsyncSession,
) -> None:
    target = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Summary Target",
    )
    viewer = await crud.get_or_create_user_from_steam(
        session=db,
        steamid64=random_steamid64(),
    )
    another = await crud.get_or_create_user_from_steam(
        session=db,
        steamid64=random_steamid64(),
    )

    await crud.create_player_follow(
        session=db,
        follower_steamid64=viewer.steamid64,
        followed_steamid64=target.steamid64,
    )
    await crud.create_player_follow(
        session=db,
        follower_steamid64=another.steamid64,
        followed_steamid64=target.steamid64,
    )
    await crud.create_player_follow(
        session=db,
        follower_steamid64=viewer.steamid64,
        followed_steamid64=another.steamid64,
    )

    summary = await crud.get_player_follow_summary(
        session=db,
        target_steamid64=target.steamid64,
        viewer_steamid64=viewer.steamid64,
    )

    assert summary.follower_count == 2
    assert summary.following_count == 0
    assert summary.viewer_is_following is True
    assert summary.viewer_is_self is False


@pytest.mark.asyncio
async def test_create_player_follow_allows_target_without_user_row(
    db: AsyncSession,
) -> None:
    follower = await crud.get_or_create_user_from_steam(
        session=db,
        steamid64=random_steamid64(),
    )
    target = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Player Only",
    )

    follow = await crud.create_player_follow(
        session=db,
        follower_steamid64=follower.steamid64,
        followed_steamid64=target.steamid64,
    )
    summary = await crud.get_player_follow_summary(
        session=db,
        target_steamid64=target.steamid64,
        viewer_steamid64=follower.steamid64,
    )

    assert follow.followed_steamid64 == target.steamid64
    assert await db.get(User, target.steamid64) is None
    assert summary.follower_count == 1
    assert summary.following_count == 0
    assert summary.viewer_is_following is True


@pytest.mark.asyncio
async def test_create_player_follow_rejects_self_follow(db: AsyncSession) -> None:
    user = await crud.get_or_create_user_from_steam(
        session=db,
        steamid64=random_steamid64(),
    )

    with pytest.raises(ValueError, match="You cannot follow yourself"):
        await crud.create_player_follow(
            session=db,
            follower_steamid64=user.steamid64,
            followed_steamid64=user.steamid64,
        )


@pytest.mark.asyncio
async def test_follow_lists_are_sorted_newest_first(db: AsyncSession) -> None:
    target = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Order Target",
    )
    follower_one = await crud.get_or_create_user_from_steam(
        session=db,
        steamid64=random_steamid64(),
    )
    follower_two = await crud.get_or_create_user_from_steam(
        session=db,
        steamid64=random_steamid64(),
    )
    followed_one = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Followed One",
    )
    followed_two = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Followed Two",
    )
    await crud.get_or_create_user_from_steam(
        session=db,
        steamid64=target.steamid64,
    )

    now = datetime.now(UTC)
    db.add(
        PlayerFollow(
            follower_steamid64=follower_one.steamid64,
            followed_steamid64=target.steamid64,
            created_at=now - timedelta(minutes=2),
        )
    )
    db.add(
        PlayerFollow(
            follower_steamid64=follower_two.steamid64,
            followed_steamid64=target.steamid64,
            created_at=now - timedelta(minutes=1),
        )
    )
    db.add(
        PlayerFollow(
            follower_steamid64=target.steamid64,
            followed_steamid64=followed_one.steamid64,
            created_at=now - timedelta(minutes=2),
        )
    )
    db.add(
        PlayerFollow(
            follower_steamid64=target.steamid64,
            followed_steamid64=followed_two.steamid64,
            created_at=now - timedelta(minutes=1),
        )
    )
    await db.commit()

    followers, follower_count = await crud.get_player_followers(
        session=db,
        target_steamid64=target.steamid64,
        offset=0,
        limit=10,
    )
    following, following_count = await crud.get_player_following(
        session=db,
        target_steamid64=target.steamid64,
        offset=0,
        limit=10,
    )

    assert follower_count == 2
    assert [player.steamid64 for player in followers] == [
        follower_two.steamid64,
        follower_one.steamid64,
    ]
    assert following_count == 2
    assert [player.steamid64 for player in following] == [
        followed_two.steamid64,
        followed_one.steamid64,
    ]
