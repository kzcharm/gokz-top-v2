from typing import Annotated

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from app import crud
from app.api.deps import SessionDep
from app.models import LiveStreamListQuery, LiveStreamsPublic
from app.services.live_streams import (
    ENABLED_LIVE_STREAM_PLATFORMS,
    fetch_live_preview_image,
    get_live_stream_stale_after,
    resolve_live_preview_url,
)

router = APIRouter(prefix="/live", tags=["live"])


@router.get("/streams", response_model=LiveStreamsPublic)
async def read_live_streams(
    session: SessionDep,
    query: Annotated[LiveStreamListQuery, Query()],
) -> LiveStreamsPublic:
    cards = await crud.read_live_stream_cards(
        session=session,
        online=query.online,
        platforms=ENABLED_LIVE_STREAM_PLATFORMS,
        stale_after=get_live_stream_stale_after(),
        preview_url_resolver=resolve_live_preview_url,
    )
    return LiveStreamsPublic(data=cards, count=len(cards))


@router.get("/preview-image")
async def proxy_live_preview_image(
    url: Annotated[str, Query(min_length=1, max_length=2000)],
) -> Response:
    try:
        content, media_type = await fetch_live_preview_image(url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Preview source returned {exc.response.status_code}",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail="Unable to fetch preview image",
        ) from exc

    return Response(
        content=content,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=60"},
    )
