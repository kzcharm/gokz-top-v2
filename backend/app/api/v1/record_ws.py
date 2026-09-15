from typing import Annotated

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.models import ModeScope, RecentWrListQuery, RecordType
from app.services.recent_wr_events import recent_wr_event_hub
from app.services.record_events import (
    build_recent_record_snapshot_event,
    recent_record_event_hub,
)

router = APIRouter(prefix="/ws", tags=["record-ws"])


@router.websocket("/records/recent")
async def websocket_recent_records(
    websocket: WebSocket,
    scope: Annotated[ModeScope, Query()] = ModeScope.OVR,
    steamid64: Annotated[str | None, Query(pattern=r"^[1-9]\d{0,18}$")] = None,
) -> None:
    await recent_record_event_hub.connect(
        websocket,
        scope=scope,
        steamid64=steamid64,
    )
    try:
        snapshot = await build_recent_record_snapshot_event(
            scope=scope,
            steamid64=steamid64,
        )
        await websocket.send_json(snapshot.model_dump(mode="json"))
        while True:
            await websocket.receive()
    except WebSocketDisconnect:
        await recent_record_event_hub.disconnect(websocket)
    except Exception:
        await recent_record_event_hub.disconnect(websocket)


@router.websocket("/records/wrs/recent")
async def websocket_recent_wrs(
    websocket: WebSocket,
    scope: Annotated[ModeScope, Query()] = ModeScope.OVR,
    map_id: Annotated[int | None, Query(ge=1)] = None,
    tier: Annotated[int | None, Query(ge=0, le=8)] = None,
    type: Annotated[RecordType | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> None:
    query = RecentWrListQuery(
        limit=limit,
        scope=scope,
        map_id=map_id,
        tier=tier,
        type=type,
    )
    await recent_wr_event_hub.connect(websocket, query=query)
    try:
        await recent_wr_event_hub.send_snapshot(websocket, query=query)
        while True:
            await websocket.receive()
    except WebSocketDisconnect:
        await recent_wr_event_hub.disconnect(websocket)
    except Exception:
        await recent_wr_event_hub.disconnect(websocket)
