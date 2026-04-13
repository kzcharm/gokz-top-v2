from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app import crud
from app.api.deps import SessionDep
from app.models import BanCompatPublicV0, BanListQuery

router = APIRouter(prefix="/bans", tags=["bans"])


@router.get("", response_model=list[BanCompatPublicV0])
async def read_bans(
    session: SessionDep,
    ban_types: Annotated[str | None, Query()] = None,
    ban_types_list: Annotated[list[str] | None, Query()] = None,
    is_expired: Annotated[bool | None, Query()] = None,
    ip: Annotated[str | None, Query()] = None,
    steamid64: Annotated[int | None, Query()] = None,
    notes_contains: Annotated[str | None, Query()] = None,
    stats_contains: Annotated[str | None, Query()] = None,
    server_id: Annotated[int | None, Query()] = None,
    created_since: Annotated[datetime | None, Query()] = None,
    updated_since: Annotated[datetime | None, Query()] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=10000)] = 100,
) -> list[BanCompatPublicV0]:
    bans, _count = await crud.read_bans(
        session=session,
        query=BanListQuery(
            ban_types=ban_types,
            ban_types_list=ban_types_list,
            is_expired=is_expired,
            ip=ip,
            steamid64=steamid64,
            notes_contains=notes_contains,
            stats_contains=stats_contains,
            server_id=server_id,
            created_since=created_since,
            updated_since=updated_since,
            offset=offset,
            limit=limit,
        ),
    )
    return [
        crud.to_ban_compat_public_v0(ban=ban, player=player)
        for ban, player in bans
    ]
