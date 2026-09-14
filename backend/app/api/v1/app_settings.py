from fastapi import APIRouter

from app import crud
from app.api.deps import SessionDep
from app.models import AppSettingsPublic

router = APIRouter(prefix="/app-settings", tags=["app-settings"])


@router.get("", response_model=AppSettingsPublic)
async def read_app_settings(*, session: SessionDep) -> AppSettingsPublic:
    community_links = await crud.get_community_links_setting(session=session)
    return AppSettingsPublic(community_links_location=community_links.location)
