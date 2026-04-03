from typing import Annotated, Any

from fastapi import APIRouter, Query

from app import crud
from app.api.deps import SessionDep
from app.models import RecordFilterCompatPublicV0

router = APIRouter(prefix="/record_filters", tags=["record_filters"])


@router.get("", response_model=list[RecordFilterCompatPublicV0])
async def read_record_filters(
    session: SessionDep,
    ids: Annotated[list[int] | None, Query()] = None,
    map_ids: Annotated[list[int] | None, Query()] = None,
    stages: Annotated[list[int] | None, Query()] = None,
    mode_ids: Annotated[list[int] | None, Query()] = None,
    tickrates: Annotated[list[int] | None, Query()] = None,
    has_teleports: Annotated[bool | None, Query()] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=10000)] = 100,
) -> Any:
    return await crud.read_record_filters_v0(
        session=session,
        ids=ids,
        map_ids=map_ids,
        stages=stages,
        mode_ids=mode_ids,
        tickrates=tickrates,
        has_teleports=has_teleports,
        offset=offset,
        limit=limit,
    )
