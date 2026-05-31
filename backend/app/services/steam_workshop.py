from __future__ import annotations

from typing import Any

import httpx

STEAM_WORKSHOP_DETAILS_URL = (
    "https://api.steampowered.com/ISteamRemoteStorage/"
    "GetPublishedFileDetails/v1/"
)


def _parse_preview_url(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    response = payload.get("response")
    if not isinstance(response, dict):
        return None
    details = response.get("publishedfiledetails")
    if not isinstance(details, list) or not details:
        return None
    first_detail = details[0]
    if not isinstance(first_detail, dict):
        return None
    preview_url = first_detail.get("preview_url")
    if not isinstance(preview_url, str):
        return None
    normalized_url = preview_url.strip()
    if not normalized_url.startswith(("http://", "https://")):
        return None
    return normalized_url


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
            data={
                "itemcount": "1",
                "publishedfileids[0]": workshop_id,
            },
        )
        response.raise_for_status()
        return _parse_preview_url(response.json())
    except (httpx.HTTPError, ValueError):
        return None
    finally:
        if should_close:
            await resolved_client.aclose()
