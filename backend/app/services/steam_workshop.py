from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import httpx
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import WorkshopPreviewUrlCache
from app.models.utils import get_datetime_utc

STEAM_WORKSHOP_DETAILS_URL = (
    "https://api.steampowered.com/ISteamRemoteStorage/"
    "GetPublishedFileDetails/v1/"
)
STEAM_WORKSHOP_DETAILS_BATCH_SIZE = 100
WORKSHOP_PREVIEW_URL_TTL = timedelta(hours=24)
WORKSHOP_PREVIEW_MISS_TTL = timedelta(hours=1)


@dataclass(frozen=True, slots=True)
class SteamWorkshopFileDetails:
    publishedfileid: str
    creator: str | None
    preview_url: str | None


def _normalize_url(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized_url = value.strip()
    if not normalized_url.startswith(("http://", "https://")):
        return None
    return normalized_url


def _parse_published_file_details(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    response = payload.get("response")
    if not isinstance(response, dict):
        return []
    details = response.get("publishedfiledetails")
    if not isinstance(details, list):
        return []
    return [detail for detail in details if isinstance(detail, dict)]


def _parse_preview_url(payload: Any) -> str | None:
    details = _parse_published_file_details(payload)
    if not details:
        return None
    return _normalize_url(details[0].get("preview_url"))


def _parse_workshop_file_detail(detail: dict[str, Any]) -> SteamWorkshopFileDetails | None:
    publishedfileid = detail.get("publishedfileid")
    if not isinstance(publishedfileid, str) or not publishedfileid.strip().isdigit():
        return None

    creator = detail.get("creator")
    normalized_creator = (
        creator.strip()
        if isinstance(creator, str) and creator.strip().isdigit()
        else None
    )
    return SteamWorkshopFileDetails(
        publishedfileid=publishedfileid.strip(),
        creator=normalized_creator,
        preview_url=_normalize_url(detail.get("preview_url")),
    )


def _workshop_details_post_data(workshop_ids: list[str]) -> dict[str, str]:
    data = {"itemcount": str(len(workshop_ids))}
    for index, workshop_id in enumerate(workshop_ids):
        data[f"publishedfileids[{index}]"] = workshop_id
    return data


async def fetch_workshop_preview_url(
    *,
    workshop_id: str,
    client: httpx.AsyncClient | None = None,
) -> str | None:
    resolved_client = client or httpx.AsyncClient(timeout=10.0)
    should_close = client is None
    try:
        response = await resolved_client.post(
            STEAM_WORKSHOP_DETAILS_URL,
            data=_workshop_details_post_data([workshop_id]),
        )
        response.raise_for_status()
        return _parse_preview_url(response.json())
    except (httpx.HTTPError, ValueError):
        return None
    finally:
        if should_close:
            await resolved_client.aclose()


def _is_cached_preview_url_fresh(
    cache_row: WorkshopPreviewUrlCache,
) -> bool:
    if cache_row.preview_url is None or cache_row.fetched_at is None:
        return False
    return cache_row.fetched_at >= get_datetime_utc() - WORKSHOP_PREVIEW_URL_TTL


def _is_cached_preview_miss_fresh(
    cache_row: WorkshopPreviewUrlCache,
) -> bool:
    if cache_row.preview_url is not None:
        return False
    return cache_row.last_attempted_at >= (
        get_datetime_utc() - WORKSHOP_PREVIEW_MISS_TTL
    )


async def get_cached_workshop_preview_url(
    *,
    session: AsyncSession,
    workshop_id: str,
) -> str | None:
    normalized_workshop_id = str(int(workshop_id))
    preview_urls = await get_cached_workshop_preview_urls(
        session=session,
        workshop_ids=[normalized_workshop_id],
    )
    return preview_urls.get(normalized_workshop_id)


async def get_cached_workshop_preview_urls(
    *,
    session: AsyncSession,
    workshop_ids: list[str],
) -> dict[str, str | None]:
    normalized_workshop_ids = list(
        dict.fromkeys(
            str(int(workshop_id.strip()))
            for workshop_id in workshop_ids
            if workshop_id.strip().isdigit()
        )
    )
    if not normalized_workshop_ids:
        return {}

    normalized_workshop_id_values = [
        int(workshop_id) for workshop_id in normalized_workshop_ids
    ]
    cache_rows = list(
        (
            await session.exec(
                select(WorkshopPreviewUrlCache).where(
                    col(WorkshopPreviewUrlCache.workshop_id).in_(
                        normalized_workshop_id_values
                    )
                )
            )
        ).all()
    )
    cache_rows_by_workshop_id = {
        str(cache_row.workshop_id): cache_row for cache_row in cache_rows
    }
    preview_urls: dict[str, str | None] = {}
    workshop_ids_to_refresh: list[str] = []
    for workshop_id in normalized_workshop_ids:
        cache_row = cache_rows_by_workshop_id.get(workshop_id)
        if cache_row is not None and _is_cached_preview_url_fresh(cache_row):
            preview_urls[workshop_id] = cache_row.preview_url
        elif cache_row is not None and _is_cached_preview_miss_fresh(cache_row):
            preview_urls[workshop_id] = None
        else:
            workshop_ids_to_refresh.append(workshop_id)

    if not workshop_ids_to_refresh:
        return preview_urls

    if len(workshop_ids_to_refresh) == 1:
        workshop_id = workshop_ids_to_refresh[0]
        refreshed_preview_urls = {
            workshop_id: await fetch_workshop_preview_url(workshop_id=workshop_id)
        }
    else:
        workshop_details = await fetch_workshop_file_details(
            workshop_ids=workshop_ids_to_refresh
        )
        refreshed_preview_urls = {
            workshop_id: (
                workshop_details[workshop_id].preview_url
                if workshop_id in workshop_details
                else None
            )
            for workshop_id in workshop_ids_to_refresh
        }

    now = get_datetime_utc()
    cache_values = [
        {
            "workshop_id": int(workshop_id),
            "preview_url": preview_url,
            "fetched_at": now if preview_url is not None else None,
            "last_attempted_at": now,
            "error_message": (
                None if preview_url is not None else "Workshop preview not found"
            ),
        }
        for workshop_id, preview_url in refreshed_preview_urls.items()
    ]
    insert_statement = postgresql_insert(WorkshopPreviewUrlCache).values(cache_values)
    await session.exec(
        insert_statement.on_conflict_do_update(
            index_elements=[WorkshopPreviewUrlCache.workshop_id],
            set_={
                "preview_url": insert_statement.excluded.preview_url,
                "fetched_at": insert_statement.excluded.fetched_at,
                "last_attempted_at": insert_statement.excluded.last_attempted_at,
                "error_message": insert_statement.excluded.error_message,
            },
        )
    )
    await session.commit()
    preview_urls.update(refreshed_preview_urls)
    return preview_urls


async def fetch_workshop_file_details(
    *,
    workshop_ids: list[str],
    client: httpx.AsyncClient | None = None,
) -> dict[str, SteamWorkshopFileDetails]:
    normalized_workshop_ids = list(
        dict.fromkeys(
            workshop_id.strip()
            for workshop_id in workshop_ids
            if workshop_id.strip().isdigit()
        )
    )
    if not normalized_workshop_ids:
        return {}

    resolved_client = client or httpx.AsyncClient(timeout=20.0)
    should_close = client is None
    results: dict[str, SteamWorkshopFileDetails] = {}
    try:
        for start in range(0, len(normalized_workshop_ids), STEAM_WORKSHOP_DETAILS_BATCH_SIZE):
            batch = normalized_workshop_ids[
                start : start + STEAM_WORKSHOP_DETAILS_BATCH_SIZE
            ]
            response = await resolved_client.post(
                STEAM_WORKSHOP_DETAILS_URL,
                data=_workshop_details_post_data(batch),
            )
            response.raise_for_status()
            for detail in _parse_published_file_details(response.json()):
                parsed = _parse_workshop_file_detail(detail)
                if parsed is not None:
                    results[parsed.publishedfileid] = parsed
    except (httpx.HTTPError, ValueError):
        return results
    finally:
        if should_close:
            await resolved_client.aclose()
    return results
