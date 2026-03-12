from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.server_events import build_server_snapshot_event, server_event_hub

router = APIRouter(prefix="/ws", tags=["server-ws"])


@router.websocket("/servers")
async def websocket_servers(websocket: WebSocket) -> None:
    await server_event_hub.connect(websocket)
    try:
        snapshot = await build_server_snapshot_event()
        await websocket.send_json(snapshot.model_dump(mode="json"))
        while True:
            await websocket.receive()
    except WebSocketDisconnect:
        await server_event_hub.disconnect(websocket)
    except Exception:
        await server_event_hub.disconnect(websocket)
