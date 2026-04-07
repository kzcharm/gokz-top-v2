from fastapi import APIRouter

from app.core.regions import list_regions
from app.models import RegionsPublic

router = APIRouter(prefix="/regions", tags=["regions"])


@router.get("/", response_model=RegionsPublic)
async def read_regions() -> RegionsPublic:
    regions = list_regions()
    return RegionsPublic(data=regions, count=len(regions))
