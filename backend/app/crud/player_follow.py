from sqlalchemy.exc import IntegrityError
from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Player, PlayerFollow, PlayerFollowSummaryPublic


async def is_player_following(
    *,
    session: AsyncSession,
    follower_steamid64: int,
    followed_steamid64: int,
) -> bool:
    follow = await session.get(
        PlayerFollow,
        (follower_steamid64, followed_steamid64),
    )
    return follow is not None


async def create_player_follow(
    *,
    session: AsyncSession,
    follower_steamid64: int,
    followed_steamid64: int,
) -> PlayerFollow:
    if follower_steamid64 == followed_steamid64:
        raise ValueError("You cannot follow yourself")

    existing_follow = await session.get(
        PlayerFollow,
        (follower_steamid64, followed_steamid64),
    )
    if existing_follow is not None:
        return existing_follow

    follow = PlayerFollow(
        follower_steamid64=follower_steamid64,
        followed_steamid64=followed_steamid64,
    )
    session.add(follow)
    try:
        await session.commit()
        await session.refresh(follow)
        return follow
    except IntegrityError:
        await session.rollback()
        existing_follow = await session.get(
            PlayerFollow,
            (follower_steamid64, followed_steamid64),
        )
        if existing_follow is None:
            raise
        return existing_follow


async def delete_player_follow(
    *,
    session: AsyncSession,
    follower_steamid64: int,
    followed_steamid64: int,
) -> bool:
    existing_follow = await session.get(
        PlayerFollow,
        (follower_steamid64, followed_steamid64),
    )
    if existing_follow is None:
        return False

    await session.delete(existing_follow)
    await session.commit()
    return True


async def get_player_follower_count(
    *,
    session: AsyncSession,
    target_steamid64: int,
) -> int:
    statement = select(func.count()).select_from(PlayerFollow).where(
        PlayerFollow.followed_steamid64 == target_steamid64
    )
    return int((await session.exec(statement)).one())


async def get_player_following_count(
    *,
    session: AsyncSession,
    target_steamid64: int,
) -> int:
    statement = select(func.count()).select_from(PlayerFollow).where(
        PlayerFollow.follower_steamid64 == target_steamid64
    )
    return int((await session.exec(statement)).one())


async def get_player_follow_summary(
    *,
    session: AsyncSession,
    target_steamid64: int,
    viewer_steamid64: int | None,
) -> PlayerFollowSummaryPublic:
    follower_count = await get_player_follower_count(
        session=session,
        target_steamid64=target_steamid64,
    )
    following_count = await get_player_following_count(
        session=session,
        target_steamid64=target_steamid64,
    )
    viewer_is_self = viewer_steamid64 == target_steamid64 if viewer_steamid64 else False
    viewer_is_following: bool | None = None
    if viewer_steamid64 is not None:
        viewer_is_following = False if viewer_is_self else await is_player_following(
            session=session,
            follower_steamid64=viewer_steamid64,
            followed_steamid64=target_steamid64,
        )

    return PlayerFollowSummaryPublic(
        follower_count=follower_count,
        following_count=following_count,
        viewer_is_following=viewer_is_following,
        viewer_is_self=viewer_is_self,
    )


async def get_player_followers(
    *,
    session: AsyncSession,
    target_steamid64: int,
    offset: int,
    limit: int,
) -> tuple[list[Player], int]:
    count_statement = select(func.count()).select_from(PlayerFollow).where(
        PlayerFollow.followed_steamid64 == target_steamid64
    )
    count = int((await session.exec(count_statement)).one())

    statement = (
        select(Player)
        .join(PlayerFollow, Player.steamid64 == PlayerFollow.follower_steamid64)
        .where(PlayerFollow.followed_steamid64 == target_steamid64)
        .order_by(col(PlayerFollow.created_at).desc(), col(Player.steamid64).desc())
        .offset(offset)
        .limit(limit)
    )
    followers = list((await session.exec(statement)).all())
    return followers, count


async def get_player_following(
    *,
    session: AsyncSession,
    target_steamid64: int,
    offset: int,
    limit: int,
) -> tuple[list[Player], int]:
    count_statement = select(func.count()).select_from(PlayerFollow).where(
        PlayerFollow.follower_steamid64 == target_steamid64
    )
    count = int((await session.exec(count_statement)).one())

    statement = (
        select(Player)
        .join(PlayerFollow, Player.steamid64 == PlayerFollow.followed_steamid64)
        .where(PlayerFollow.follower_steamid64 == target_steamid64)
        .order_by(col(PlayerFollow.created_at).desc(), col(Player.steamid64).desc())
        .offset(offset)
        .limit(limit)
    )
    following = list((await session.exec(statement)).all())
    return following, count
