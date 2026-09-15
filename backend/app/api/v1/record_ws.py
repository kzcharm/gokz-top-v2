from typing import Annotated

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.models import ModeScope
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
