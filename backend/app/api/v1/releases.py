from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import OptionalCurrentUser, SessionDep
from app.models import GitHubReleasesPublic
from app.services.github_releases import (
    GitHubReleasesUnavailableError,
    read_github_releases,
)

router = APIRouter(prefix="/releases", tags=["releases"])


@router.get("", response_model=GitHubReleasesPublic)
async def read_releases(
    *,
    session: SessionDep,
    current_user: OptionalCurrentUser,
    limit: Annotated[int, Query(ge=1, le=20)] = 20,
) -> GitHubReleasesPublic:
    try:
        return await read_github_releases(
            session=session,
            limit=limit,
            viewer_steamid64=(current_user.steamid64 if current_user else None),
        )
    except GitHubReleasesUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
