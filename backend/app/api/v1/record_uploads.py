"""Server-group authenticated writes on the existing records resource."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from app.api.deps import SessionDep
from app.api.v1.player_sessions import _get_server_group_from_api_key
from app.models import ServerGroup
from app.models.record_upload import GlobalApiClaim, RecordCheck, RecordFinish
from app.services.record_ingestion import accept_record, check_record

router = APIRouter(prefix="/records", tags=["records"])


async def authenticated_group(
    session: SessionDep,
    x_server_group_key: Annotated[str | None, Header()] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> ServerGroup:
    return await _get_server_group_from_api_key(
        session=session,
        x_server_group_key=x_server_group_key,
        authorization=authorization,
    )


Group = Annotated[ServerGroup, Depends(authenticated_group)]


@router.post("/check")
async def check(
    session: SessionDep, group: Group, payload: RecordCheck
) -> dict[str, Any]:
    result, _ = await check_record(session, group, payload)
    await session.commit()
    return result


@router.post("")
async def create(
    session: SessionDep,
    group: Group,
    payload: RecordFinish,
    idempotency_key: Annotated[str, Header(min_length=1, max_length=128)],
) -> dict[str, Any]:
    return await accept_record(session, group, payload, idempotency_key)


@router.put("/{record_uuid}/globalapi")
async def attach_globalapi(
    session: SessionDep, group: Group, record_uuid: uuid.UUID, payload: GlobalApiClaim
) -> dict[str, Any]:
    from app.services.record_reconciliation import submit_claim

    return await submit_claim(session, group, record_uuid, payload.globalapi_id)


@router.put("/{record_uuid}/replay")
async def upload_replay(
    session: SessionDep, group: Group, record_uuid: uuid.UUID, request: Request
) -> dict[str, Any]:
    from app.services.record_replay_upload import accept_replay

    # Bound both chunked and Content-Length uploads. No unbounded request.body().
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > 256 * 1024 * 1024:
            raise HTTPException(413, "Replay exceeds the 256 MiB upload limit")
        data.extend(chunk)
    return await accept_replay(session, group, record_uuid, bytes(data))
