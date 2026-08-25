import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import (
    AdminPlayerSocialLinkPublic,
    Player,
    PlayerRefPublic,
    PlayerSocialLink,
    PlayerSocialLinkPublic,
    PlayerSocialPlatform,
)
from app.services.player_social_links import (
    SOCIAL_PLATFORM_ORDER,
    build_player_social_link_url,
    parse_player_social_link_url,
)


class PlayerSocialLinkConflictError(ValueError):
    pass


def parse_social_link_or_raise(url: str) -> tuple[PlayerSocialPlatform, str]:
    parsed = parse_player_social_link_url(url)
    if parsed is None:
        raise ValueError("Unsupported or invalid social profile URL")
    return parsed.platform, parsed.account_identifier


async def get_player_social_link(
    *, session: AsyncSession, id: uuid.UUID
) -> PlayerSocialLink | None:
    return await session.get(PlayerSocialLink, id)


async def list_player_social_links(
    *, session: AsyncSession, player_steamid64: int
) -> list[PlayerSocialLink]:
    statement = (
        select(PlayerSocialLink)
        .where(col(PlayerSocialLink.player_steamid64) == player_steamid64)
        .order_by(
            col(PlayerSocialLink.platform).asc(),
            col(PlayerSocialLink.created_at).asc(),
        )
    )
    links = list((await session.exec(statement)).all())
    return sorted(
        links,
        key=lambda link: (
            SOCIAL_PLATFORM_ORDER.index(link.platform),
            link.created_at,
            str(link.id),
        ),
    )


async def create_player_social_link(
    *,
    session: AsyncSession,
    player_steamid64: int,
    url: str,
    verified: bool = False,
) -> PlayerSocialLink:
    platform, account_identifier = parse_social_link_or_raise(url)
    link = PlayerSocialLink(
        player_steamid64=player_steamid64,
        platform=platform,
        account_identifier=account_identifier,
        verified=verified,
    )
    session.add(link)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise PlayerSocialLinkConflictError(
            "Social link already exists for this player or verified account"
        ) from exc

    await session.refresh(link)
    return link


async def update_player_social_link(
    *,
    session: AsyncSession,
    link: PlayerSocialLink,
    url: str | None = None,
    verified: bool | None = None,
    show_on_site: bool | None = None,
) -> PlayerSocialLink:
    if url is not None:
        platform, account_identifier = parse_social_link_or_raise(url)
        if (
            link.platform != platform
            or link.account_identifier != account_identifier
        ):
            link.metadata_json = None
        link.platform = platform
        link.account_identifier = account_identifier
    if verified is not None:
        link.verified = verified
    if show_on_site is not None:
        link.show_on_site = show_on_site

    link.updated_at = datetime.now(UTC)
    session.add(link)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise PlayerSocialLinkConflictError(
            "Social link already exists for this player or verified account"
        ) from exc

    await session.refresh(link)
    return link


async def update_player_social_link_metadata(
    *,
    session: AsyncSession,
    link: PlayerSocialLink,
    metadata_json: dict[str, Any] | None,
) -> PlayerSocialLink:
    link.metadata_json = metadata_json
    link.updated_at = datetime.now(UTC)
    session.add(link)
    await session.commit()
    await session.refresh(link)
    return link


async def delete_player_social_link(
    *, session: AsyncSession, link: PlayerSocialLink
) -> None:
    await session.delete(link)
    await session.commit()


async def read_admin_player_social_links(
    *,
    session: AsyncSession,
    offset: int,
    limit: int,
    steamid64: int | None = None,
    platform: PlayerSocialPlatform | None = None,
    verified: bool | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> tuple[list[tuple[PlayerSocialLink, Player]], int]:
    filters = []
    if steamid64 is not None:
        filters.append(col(PlayerSocialLink.player_steamid64) == steamid64)
    if platform is not None:
        filters.append(col(PlayerSocialLink.platform) == platform)
    if verified is not None:
        filters.append(col(PlayerSocialLink.verified) == verified)

    base_statement = select(PlayerSocialLink)
    count_statement = select(func.count()).select_from(PlayerSocialLink)
    if filters:
        base_statement = base_statement.where(*filters)
        count_statement = count_statement.where(*filters)

    count = int((await session.exec(count_statement)).one())

    sort_column: Any = col(PlayerSocialLink.created_at)
    if sort_by == "updated_at":
        sort_column = col(PlayerSocialLink.updated_at)
    elif sort_by == "platform":
        sort_column = col(PlayerSocialLink.platform)
    sort_direction = sort_column.asc() if sort_order == "asc" else sort_column.desc()

    statement = (
        select(PlayerSocialLink, Player)
        .outerjoin(Player, col(Player.steamid64) == col(PlayerSocialLink.player_steamid64))
        .where(*filters)
        .order_by(
            sort_direction,
            col(PlayerSocialLink.player_steamid64).desc(),
            col(PlayerSocialLink.id).desc(),
        )
        .offset(offset)
        .limit(limit)
    )
    rows = list((await session.exec(statement)).all())
    return rows, count


def to_player_social_link_public(
    *, link: PlayerSocialLink
) -> PlayerSocialLinkPublic:
    return PlayerSocialLinkPublic(
        id=link.id,
        player_steamid64=str(link.player_steamid64),
        platform=link.platform,
        account_identifier=link.account_identifier,
        verified=link.verified,
        show_on_site=link.show_on_site,
        url=build_player_social_link_url(
            platform=link.platform,
            account_identifier=link.account_identifier,
        ),
        created_at=link.created_at,
        updated_at=link.updated_at,
    )


def to_player_social_link_publics(
    *, links: Sequence[PlayerSocialLink]
) -> list[PlayerSocialLinkPublic]:
    return [to_player_social_link_public(link=link) for link in links]


def to_admin_player_social_link_public(
    *, link: PlayerSocialLink, player: Player | None = None
) -> AdminPlayerSocialLinkPublic:
    public = to_player_social_link_public(link=link)
    return AdminPlayerSocialLinkPublic(
        **public.model_dump(),
        player=(
            PlayerRefPublic(
                steamid64=str(player.steamid64),
                display_name=player.alias or player.name,
            )
            if player is not None
            else None
        ),
    )
