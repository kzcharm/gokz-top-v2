from typing import Annotated

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from app import crud
from app.api.deps import SessionDep
from app.models import (
    MediaPostsPublic,
    MediaPostsQuery,
    MediaPostViewCountRefreshRequest,
    MediaPostViewCountsRefreshPublic,
)
from app.services.bilibili_media import fetch_bilibili_thumbnail

router = APIRouter(prefix="/media", tags=["media"])


@router.get("/thumbnail")
async def proxy_bilibili_thumbnail(
    url: Annotated[str, Query(min_length=1, max_length=2000)],
) -> Response:
    try:
        content, media_type = await fetch_bilibili_thumbnail(url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Thumbnail source returned {exc.response.status_code}",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail="Unable to fetch Bilibili thumbnail",
        ) from exc
    return Response(
        content=content,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/posts", response_model=MediaPostsPublic)
async def read_media_posts(
    session: SessionDep,
    query: Annotated[MediaPostsQuery, Query()],
) -> MediaPostsPublic:
    return await crud.read_media_posts(
        session=session,
        cursor=query.cursor,
        limit=query.limit,
        steamid64=query.steamid64,
        from_=query.from_,
        to=query.to,
    )


@router.post("/posts/view-counts", response_model=MediaPostViewCountsRefreshPublic)
async def refresh_media_post_view_counts(
    session: SessionDep,
    body: MediaPostViewCountRefreshRequest,
) -> MediaPostViewCountsRefreshPublic:
    return await crud.refresh_media_post_view_counts(
        session=session, post_ids=body.post_ids
    )
