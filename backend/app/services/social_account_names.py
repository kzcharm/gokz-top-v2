import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import httpx
from pydantic import BaseModel, ValidationError
from sqlalchemy import case, cast, func, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm.attributes import set_committed_value
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models import PlayerSocialLink, PlayerSocialPlatform
from app.models.utils import get_sqlmodel_table


class SocialAccountNameCache(BaseModel):
    account_identifier: str
    name: str | None
    checked_at: datetime


def get_account_name_cache(link: PlayerSocialLink) -> SocialAccountNameCache | None:
    if not isinstance(link.metadata_json, dict):
        return None
    try:
        cache = SocialAccountNameCache.model_validate(
            (link.metadata_json or {}).get("account_name_cache")
        )
    except ValidationError:
        return None
    if cache.account_identifier != link.account_identifier:
        return None
    if cache.checked_at.tzinfo is None:
        return None
    return cache


async def fetch_social_account_name(
    *, platform: PlayerSocialPlatform, account_identifier: str
) -> str | None:
    if platform in {PlayerSocialPlatform.GITHUB, PlayerSocialPlatform.X}:
        return account_identifier
    if platform == PlayerSocialPlatform.DISCORD:
        # Discord names are captured during OAuth; public ID lookup requires a bot.
        return None

    async with httpx.AsyncClient(timeout=5.0) as client:
        if platform == PlayerSocialPlatform.BILIBILI:
            from app.services.bilibili_social_link_verification import _bilibili_headers

            response = await client.get(
                "https://api.bilibili.com/x/web-interface/card",
                params={"mid": account_identifier},
                headers=_bilibili_headers(),
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("code") != 0:
                return None
            name = payload["data"]["card"].get("name")
        elif platform == PlayerSocialPlatform.YOUTUBE:
            if not settings.YOUTUBE_API_KEY:
                return None
            from app.services.video_platform_followers import _youtube_channel_params

            response = await client.get(
                "https://www.googleapis.com/youtube/v3/channels",
                params={
                    "part": "snippet",
                    "key": settings.YOUTUBE_API_KEY,
                    **_youtube_channel_params(account_identifier),
                },
            )
            response.raise_for_status()
            name = response.json()["items"][0]["snippet"].get("title")
        elif platform == PlayerSocialPlatform.TWITCH:
            if not settings.TWITCH_CLIENT_ID or not settings.TWITCH_CLIENT_SECRET:
                return None
            from app.services.live_streams import _get_twitch_app_access_token

            token = await _get_twitch_app_access_token()
            response = await client.get(
                "https://api.twitch.tv/helix/users",
                params={"login": account_identifier},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Client-Id": settings.TWITCH_CLIENT_ID,
                },
            )
            response.raise_for_status()
            name = response.json()["data"][0].get("display_name")
        else:
            return None
    return name.strip()[:255] if isinstance(name, str) and name.strip() else None


async def refresh_social_account_names(
    *, session: AsyncSession, links: Sequence[PlayerSocialLink]
) -> None:
    now = datetime.now(UTC)
    stale = []
    for link in links:
        cache = get_account_name_cache(link)
        ttl = timedelta(days=1) if cache and cache.name else timedelta(hours=1)
        if cache is None or cache.checked_at + ttl <= now:
            stale.append((link, cache))
    if not stale:
        return

    # Release the read transaction before waiting on external providers.
    await session.commit()
    semaphore = asyncio.Semaphore(5)

    async def fetch(link: PlayerSocialLink) -> str | None:
        async with semaphore:
            try:
                return await fetch_social_account_name(
                    platform=link.platform, account_identifier=link.account_identifier
                )
            except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
                return None

    tasks = [asyncio.create_task(fetch(link)) for link, _ in stale]
    _, pending = await asyncio.wait(tasks, timeout=8.0)
    for task in pending:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)

    table = get_sqlmodel_table(PlayerSocialLink)
    for (link, previous), task in zip(stale, tasks, strict=True):
        if task.cancelled():
            continue
        name = task.result() or (previous.name if previous else None)
        cache = SocialAccountNameCache(
            account_identifier=link.account_identifier, name=name, checked_at=now
        )
        metadata = {"account_name_cache": cache.model_dump(mode="json")}
        # Merge only this cache key, preserving concurrent verification metadata.
        await session.execute(
            update(table)
            .where(
                table.c.id == link.id,
                table.c.platform == link.platform,
                table.c.account_identifier == link.account_identifier,
            )
            .values(
                metadata_json=case(
                    (
                        func.jsonb_typeof(table.c.metadata_json) == "object",
                        table.c.metadata_json,
                    ),
                    else_=cast({}, JSONB),
                ).op("||")(cast(metadata, JSONB))
            )
        )
        # Keep the response current without marking the ORM object as dirty.
        set_committed_value(
            link,
            "metadata_json",
            {
                **(link.metadata_json if isinstance(link.metadata_json, dict) else {}),
                **metadata,
            },
        )
    await session.commit()
