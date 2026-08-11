from typing import Annotated

from fastapi import APIRouter, Query

from app import crud
from app.api.deps import SessionDep
from app.models import (
    MediaPostsPublic,
    MediaPostsQuery,
    MediaPostViewCountRefreshRequest,
    MediaPostViewCountsRefreshPublic,
)

router = APIRouter(prefix="/media", tags=["media"])


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
