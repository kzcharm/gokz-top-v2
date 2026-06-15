from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

STEAM_WORKSHOP_DETAILS_URL = (
    "https://api.steampowered.com/ISteamRemoteStorage/"
    "GetPublishedFileDetails/v1/"
)
STEAM_WORKSHOP_DETAILS_BATCH_SIZE = 100


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
