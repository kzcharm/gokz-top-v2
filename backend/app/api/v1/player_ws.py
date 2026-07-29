from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.player_steam_profile_events import player_steam_profile_event_hub

router = APIRouter(prefix="/ws", tags=["player-ws"])


@router.websocket("/players")
async def websocket_players(websocket: WebSocket) -> None:
    await player_steam_profile_event_hub.connect(websocket)
    try:
        while True:
            await websocket.receive()
    except WebSocketDisconnect:
        await player_steam_profile_event_hub.disconnect(websocket)
    except Exception:
        await player_steam_profile_event_hub.disconnect(websocket)
