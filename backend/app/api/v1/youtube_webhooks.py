from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response, status

from app.services.youtube_media import (
    is_youtube_websub_topic,
    schedule_youtube_media_sync,
    verify_youtube_websub_signature,
    youtube_websub_is_configured,
)

router = APIRouter(prefix="/webhooks", tags=["youtube-webhooks"])


def ensure_youtube_websub_configured() -> None:
    if not youtube_websub_is_configured():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)


@router.get("/youtube", include_in_schema=False)
async def verify_youtube_websub_subscription(
    mode: Annotated[str | None, Query(alias="hub.mode")] = None,
    topic: Annotated[str | None, Query(alias="hub.topic")] = None,
    challenge: Annotated[str | None, Query(alias="hub.challenge")] = None,
) -> Response:
    ensure_youtube_websub_configured()
    if (
        mode != "subscribe"
        or not topic
        or not challenge
        or not is_youtube_websub_topic(topic)
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)
    return Response(content=challenge, media_type="text/plain")


@router.post(
    "/youtube", include_in_schema=False, status_code=status.HTTP_204_NO_CONTENT
)
async def receive_youtube_websub_notification(
    request: Request,
    signature: Annotated[str | None, Header(alias="X-Hub-Signature")] = None,
) -> Response:
    ensure_youtube_websub_configured()
    if not verify_youtube_websub_signature(
        body=await request.body(), signature=signature
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    schedule_youtube_media_sync()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
