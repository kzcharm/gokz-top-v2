from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.record_events import (
    build_recent_record_snapshot_event,
    recent_record_event_hub,
)

router = APIRouter(prefix="/ws", tags=["record-ws"])


@router.websocket("/records/recent")
async def websocket_recent_records(websocket: WebSocket) -> None:
    await recent_record_event_hub.connect(websocket)
    try:
        snapshot = await build_recent_record_snapshot_event()
        await websocket.send_json(snapshot.model_dump(mode="json"))
        while True:
            await websocket.receive()
    except WebSocketDisconnect:
        await recent_record_event_hub.disconnect(websocket)
    except Exception:
        await recent_record_event_hub.disconnect(websocket)
