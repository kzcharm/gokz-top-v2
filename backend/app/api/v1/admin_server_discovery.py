from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_active_superuser
from app.models import ServerDiscoveryRunPublic, User
from app.services.server_query import ServerQueryError
from app.services.server_status import (
    SERVER_DISCOVERY_ENABLED,
    run_server_discovery_cycle,
)

router = APIRouter(prefix="/admin", tags=["admin-servers"])
CurrentSuperuser = Annotated[User, Depends(get_current_active_superuser)]


@router.post("/server-discovery-runs", response_model=ServerDiscoveryRunPublic)
async def trigger_server_discovery(
    current_user: CurrentSuperuser,
) -> ServerDiscoveryRunPublic:
    del current_user
    if not SERVER_DISCOVERY_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="Server discovery is temporarily disabled",
        )
    try:
        result = await run_server_discovery_cycle()
    except ServerQueryError as exc:
        raise HTTPException(
            status_code=503,
            detail="Unable to query Steam server list",
        ) from exc

    return ServerDiscoveryRunPublic(
        started_at=result.started_at,
        completed_at=result.completed_at,
        regions_scanned=result.regions_scanned,
        candidate_count=result.candidate_count,
        upserted_count=result.upserted_count,
    )
