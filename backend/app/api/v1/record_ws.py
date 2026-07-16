from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.models import ModeScope
from app.services.record_events import (
    build_recent_record_snapshot_event,
    recent_record_event_hub,
)

router = APIRouter(prefix="/ws", tags=["record-ws"])


@router.websocket("/records/recent")
async def websocket_recent_records(websocket: WebSocket) -> None:
    scope = ModeScope(websocket.query_params.get("scope", ModeScope.OVR.value))
    await recent_record_event_hub.connect(websocket, scope=scope)
    try:
        snapshot = await build_recent_record_snapshot_event(scope=scope)
        await websocket.send_json(snapshot.model_dump(mode="json"))
        while True:
            await websocket.receive()
    except WebSocketDisconnect:
        await recent_record_event_hub.disconnect(websocket)
    except Exception:
        await recent_record_event_hub.disconnect(websocket)
