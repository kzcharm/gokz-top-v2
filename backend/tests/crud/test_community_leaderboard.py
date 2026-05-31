from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.models import (
    Ban,
    BanType,
    CommunityLeaderboardListQuery,
    Player,
    PlayerSocialLink,
    PlayerSocialPlatform,
    PlayerVideoPlatformFollowerCache,
)
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


async def _create_viewer(*, db: AsyncSession) -> Player:
    user = await crud.get_or_create_user_from_steam(
        session=db,
        steamid64=random_steamid64(),
    )
    return user


@pytest.mark.asyncio
async def test_read_community_leaderboard_ranks_profile_views(
    db: AsyncSession,
) -> None:
    first = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Most Viewed",
    )
    tied_lower_steamid64, tied_higher_steamid64 = sorted(
        [random_steamid64(), random_steamid64()]
    )
    second = await _create_player(
        db=db,
        steamid64=tied_lower_steamid64,
        name="Tied Lower SteamID",
    )
    third = await _create_player(
        db=db,
        steamid64=tied_higher_steamid64,
        name="Tied Higher SteamID",
    )
    viewers = [await _create_viewer(db=db) for _index in range(7)]
    now = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)

    for viewer in viewers[:3]:
        await crud.create_player_profile_view(
            session=db,
            viewer_steamid64=viewer.steamid64,
            target_steamid64=first.steamid64,
            now=now,
        )
    await crud.create_player_profile_view(
        session=db,
        viewer_steamid64=viewers[0].steamid64,
        target_steamid64=first.steamid64,
        now=now + timedelta(days=1),
    )
    for target in (second, third):
        for viewer in viewers[3:5]:
            await crud.create_player_profile_view(
                session=db,
                viewer_steamid64=viewer.steamid64,
                target_steamid64=target.steamid64,
                now=now,
            )

    data, count = await crud.read_community_leaderboard(
        session=db,
        query=CommunityLeaderboardListQuery(
            sort_by="views_count",
            offset=1,
            limit=2,
        ),
    )

    assert count == 3
    assert [
        (
            entry.rank,
            entry.player.steamid64,
            entry.views_count,
            entry.unique_visitors,
            entry.likes,
            entry.unique_likers,
        )
        for entry in data
    ] == [
        (2, str(second.steamid64), 2, 2, 0, 0),
        (3, str(third.steamid64), 2, 2, 0, 0),
    ]


@pytest.mark.asyncio
async def test_read_community_leaderboard_ranks_likes(
    db: AsyncSession,
) -> None:
    liked = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Most Liked",
    )
    less_liked = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Less Liked",
    )
    viewers = [await _create_viewer(db=db) for _index in range(4)]
    now = datetime(2026, 5, 2, 12, 0, tzinfo=UTC)

    for viewer in viewers[:3]:
        await crud.create_player_like(
            session=db,
            viewer_steamid64=viewer.steamid64,
            target_steamid64=liked.steamid64,
            now=now,
        )
    await crud.create_player_like(
        session=db,
        viewer_steamid64=viewers[0].steamid64,
        target_steamid64=liked.steamid64,
        now=now + timedelta(days=1),
    )
    await crud.create_player_like(
        session=db,
        viewer_steamid64=viewers[3].steamid64,
        target_steamid64=less_liked.steamid64,
        now=now,
    )

    data, count = await crud.read_community_leaderboard(
        session=db,
        query=CommunityLeaderboardListQuery(sort_by="likes", include_count=False),
    )

    assert count == -1
    assert [
        (
            entry.rank,
            entry.player.steamid64,
            entry.views_count,
            entry.unique_visitors,
            entry.likes,
            entry.unique_likers,
        )
        for entry in data
    ] == [
        (1, str(liked.steamid64), 0, 0, 4, 3),
        (2, str(less_liked.steamid64), 0, 0, 1, 1),
    ]


@pytest.mark.asyncio
async def test_read_community_leaderboard_returns_highest_verified_video_followers(
    db: AsyncSession,
) -> None:
    target = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Streamer",
    )
    viewer = await _create_viewer(db=db)
    now = datetime(2026, 5, 2, 12, 0, tzinfo=UTC)

    await crud.create_player_like(
        session=db,
        viewer_steamid64=viewer.steamid64,
        target_steamid64=target.steamid64,
        now=now,
    )
    bilibili_link = PlayerSocialLink(
        player_steamid64=target.steamid64,
        platform=PlayerSocialPlatform.BILIBILI,
        account_identifier="123456",
        verified=True,
    )
    youtube_link = PlayerSocialLink(
        player_steamid64=target.steamid64,
        platform=PlayerSocialPlatform.YOUTUBE,
        account_identifier="@streamer",
        verified=True,
    )
    twitch_link = PlayerSocialLink(
        player_steamid64=target.steamid64,
        platform=PlayerSocialPlatform.TWITCH,
        account_identifier="streamer",
        verified=False,
    )
    db.add_all([bilibili_link, youtube_link, twitch_link])
    await db.commit()
    for link in (bilibili_link, youtube_link, twitch_link):
        await db.refresh(link)

    fetched_at = datetime(2100, 1, 1, tzinfo=UTC)
    db.add_all(
        [
            PlayerVideoPlatformFollowerCache(
                social_link_id=bilibili_link.id,
                player_steamid64=target.steamid64,
                platform=bilibili_link.platform,
                account_identifier=bilibili_link.account_identifier,
                follower_count=250,
                fetched_at=fetched_at,
                last_attempted_at=fetched_at,
            ),
            PlayerVideoPlatformFollowerCache(
                social_link_id=youtube_link.id,
                player_steamid64=target.steamid64,
                platform=youtube_link.platform,
                account_identifier=youtube_link.account_identifier,
                follower_count=900,
                fetched_at=fetched_at,
                last_attempted_at=fetched_at,
            ),
            PlayerVideoPlatformFollowerCache(
                social_link_id=twitch_link.id,
                player_steamid64=target.steamid64,
                platform=twitch_link.platform,
                account_identifier=twitch_link.account_identifier,
                follower_count=2000,
                fetched_at=fetched_at,
                last_attempted_at=fetched_at,
            ),
        ]
    )
    await db.commit()

    data, count = await crud.read_community_leaderboard(
        session=db,
        query=CommunityLeaderboardListQuery(sort_by="likes"),
    )

    assert count == 1
    assert data[0].video_platform_followers is not None
    assert data[0].video_platform_followers.platform == PlayerSocialPlatform.YOUTUBE
    assert data[0].video_platform_followers.followers_count == 900
    assert data[0].video_platform_followers.url == "https://www.youtube.com/@streamer"


@pytest.mark.asyncio
async def test_read_community_leaderboard_sorts_by_platform_followers(
    db: AsyncSession,
) -> None:
    most_followed = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Most Followed",
    )
    less_followed = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Less Followed",
    )
    fetched_at = datetime(2100, 1, 1, tzinfo=UTC)
    most_link = PlayerSocialLink(
        player_steamid64=most_followed.steamid64,
        platform=PlayerSocialPlatform.TWITCH,
        account_identifier="mostfollowed",
        verified=True,
    )
    less_link = PlayerSocialLink(
        player_steamid64=less_followed.steamid64,
        platform=PlayerSocialPlatform.BILIBILI,
        account_identifier="123456",
        verified=True,
    )
    db.add_all([most_link, less_link])
    await db.commit()
    await db.refresh(most_link)
    await db.refresh(less_link)
    db.add_all(
        [
            PlayerVideoPlatformFollowerCache(
                social_link_id=most_link.id,
                player_steamid64=most_followed.steamid64,
                platform=most_link.platform,
                account_identifier=most_link.account_identifier,
                follower_count=10_000,
                fetched_at=fetched_at,
                last_attempted_at=fetched_at,
            ),
            PlayerVideoPlatformFollowerCache(
                social_link_id=less_link.id,
                player_steamid64=less_followed.steamid64,
                platform=less_link.platform,
                account_identifier=less_link.account_identifier,
                follower_count=500,
                fetched_at=fetched_at,
                last_attempted_at=fetched_at,
            ),
        ]
    )
    await db.commit()

    data, count = await crud.read_community_leaderboard(
        session=db,
        query=CommunityLeaderboardListQuery(sort_by="platform_followers"),
    )

    assert count == 2
    assert [
        (
            entry.rank,
            entry.player.steamid64,
            entry.video_platform_followers.followers_count
            if entry.video_platform_followers
            else None,
        )
        for entry in data
    ] == [
        (1, str(most_followed.steamid64), 10_000),
        (2, str(less_followed.steamid64), 500),
    ]


@pytest.mark.asyncio
async def test_read_community_leaderboard_sorts_by_unique_likers(
    db: AsyncSession,
) -> None:
    most_unique = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Most Unique Likers",
    )
    repeated_liker = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Repeated Liker",
    )
    viewers = [await _create_viewer(db=db) for _index in range(3)]
    now = datetime(2026, 5, 2, 12, 0, tzinfo=UTC)

    for viewer in viewers[:2]:
        await crud.create_player_like(
            session=db,
            viewer_steamid64=viewer.steamid64,
            target_steamid64=most_unique.steamid64,
            now=now,
        )
    for day_offset in range(3):
        await crud.create_player_like(
            session=db,
            viewer_steamid64=viewers[2].steamid64,
            target_steamid64=repeated_liker.steamid64,
            now=now + timedelta(days=day_offset),
        )

    data, count = await crud.read_community_leaderboard(
        session=db,
        query=CommunityLeaderboardListQuery(sort_by="unique_likers"),
    )

    assert count == 2
    assert [
        (entry.rank, entry.player.steamid64, entry.likes, entry.unique_likers)
        for entry in data
    ] == [
        (1, str(most_unique.steamid64), 2, 2),
        (2, str(repeated_liker.steamid64), 3, 1),
    ]


@pytest.mark.asyncio
async def test_read_community_leaderboard_excludes_zero_value_sort_results(
    db: AsyncSession,
) -> None:
    viewed_only = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Viewed Only",
    )
    liked = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Liked",
    )
    viewer = await _create_viewer(db=db)
    now = datetime(2026, 5, 2, 12, 0, tzinfo=UTC)

    await crud.create_player_profile_view(
        session=db,
        viewer_steamid64=viewer.steamid64,
        target_steamid64=viewed_only.steamid64,
        now=now,
    )
    await crud.create_player_like(
        session=db,
        viewer_steamid64=viewer.steamid64,
        target_steamid64=liked.steamid64,
        now=now,
    )

    data, count = await crud.read_community_leaderboard(
        session=db,
        query=CommunityLeaderboardListQuery(sort_by="likes", limit=100),
    )

    assert count == 1
    assert [(entry.rank, entry.player.steamid64, entry.likes) for entry in data] == [
        (1, str(liked.steamid64), 1),
    ]


@pytest.mark.asyncio
async def test_read_community_leaderboard_excludes_active_banned_players(
    db: AsyncSession,
) -> None:
    banned = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Banned Popular Player",
    )
    visible = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Visible Player",
    )
    viewers = [await _create_viewer(db=db) for _index in range(4)]
    now = datetime(2026, 5, 3, 12, 0, tzinfo=UTC)

    for viewer in viewers[:3]:
        await crud.create_player_like(
            session=db,
            viewer_steamid64=viewer.steamid64,
            target_steamid64=banned.steamid64,
            now=now,
        )
    await crud.create_player_like(
        session=db,
        viewer_steamid64=viewers[3].steamid64,
        target_steamid64=visible.steamid64,
        now=now,
    )
    db.add(
        Ban(
            ban_type=BanType.BHOP_HACK,
            expires_at=None,
            steamid64=banned.steamid64,
            notes="active ban",
            stats=None,
            server_id=None,
            updated_by_steamid64=None,
        )
    )
    await db.commit()

    data, count = await crud.read_community_leaderboard(
        session=db,
        query=CommunityLeaderboardListQuery(sort_by="likes"),
    )

    assert count == 1
    assert [(entry.rank, entry.player.steamid64, entry.likes) for entry in data] == [
        (1, str(visible.steamid64), 1),
    ]
