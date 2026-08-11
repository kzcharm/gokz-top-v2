from typing import Annotated

from fastapi import APIRouter, Query

from app import crud
from app.api.deps import SessionDep
from app.models import MediaPostsPublic, MediaPostsQuery

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
