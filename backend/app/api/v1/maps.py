import logging
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app import crud
from app.api.deps import SessionDep, get_current_active_superuser
from app.models import MapPublic, MapSyncResult, RecordScope
from app.services.globalapi_maps_sync import (
    GlobalAPIMapsSyncError,
    sync_maps_from_globalapi,
)

router = APIRouter(prefix="/maps", tags=["maps"])
logger = logging.getLogger(__name__)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.year >= 1900 else None
    except ValueError:
        return None


@router.get("", response_model=list[MapPublic])
async def read_maps(
    session: SessionDep,
    scope: RecordScope = RecordScope.OVR,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=10000)] = 100,
    id: Annotated[list[int] | None, Query()] = None,
    name: Annotated[str | None, Query()] = None,
    larger_than_filesize: Annotated[int | None, Query()] = None,
    smaller_than_filesize: Annotated[int | None, Query()] = None,
    is_validated: Annotated[bool | None, Query()] = None,
    difficulty: Annotated[int | None, Query()] = None,
    created_since: Annotated[str | None, Query()] = None,
    updated_since: Annotated[str | None, Query()] = None,
) -> Any:
    maps = await crud.read_maps_v1(
        session=session,
        scope=scope,
        offset=offset,
        limit=limit,
        id=id,
        name=name,
        larger_than_filesize=larger_than_filesize,
        smaller_than_filesize=smaller_than_filesize,
        is_validated=is_validated,
        difficulty=difficulty,
        created_since=_parse_datetime(created_since),
        updated_since=_parse_datetime(updated_since),
    )
    return [
        crud.to_map_public(map_obj=map_obj, difficulty=difficulty)
        for map_obj, difficulty in maps
    ]


@router.get("/name/{map_name}", response_model=MapPublic)
async def read_map_by_name(
    session: SessionDep,
    map_name: str,
    scope: RecordScope = RecordScope.OVR,
) -> Any:
    map_obj = await crud.get_map_by_name(session=session, map_name=map_name)
    if not map_obj:
        raise HTTPException(status_code=404, detail="Map not found")
    scoped_difficulty = (
        await crud.load_scoped_course_tiers(
            session=session,
            course_keys=[(map_obj.id, 0)],
            scope=scope,
        )
    )[(map_obj.id, 0)]
    return crud.to_map_public(map_obj=map_obj, difficulty=scoped_difficulty)


@router.get("/{id:int}", response_model=MapPublic)
async def read_map_by_id(
    session: SessionDep,
    id: int,
    scope: RecordScope = RecordScope.OVR,
) -> Any:
    map_obj = await crud.get_map_by_id(session=session, id=id)
    if not map_obj:
        raise HTTPException(status_code=404, detail="Map not found")
    scoped_difficulty = (
        await crud.load_scoped_course_tiers(
            session=session,
            course_keys=[(map_obj.id, 0)],
            scope=scope,
        )
    )[(map_obj.id, 0)]
    return crud.to_map_public(map_obj=map_obj, difficulty=scoped_difficulty)


@router.post(
    "/sync",
    response_model=MapSyncResult,
    dependencies=[Depends(get_current_active_superuser)],
)
async def trigger_map_sync(
    session: SessionDep,
) -> Any:
    try:
        return await sync_maps_from_globalapi(session=session)
    except GlobalAPIMapsSyncError as exc:
        logger.warning("GlobalAPI map sync failed: %s", exc)
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected map sync failure")
        raise HTTPException(
            status_code=500, detail="Failed to sync maps due to internal error"
        ) from exc
