"""Compatibility API for map pronunciations backed by the shared name service."""

from typing import cast

import httpx  # noqa: F401
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Map, MapPronunciation, MapPronunciationPublic
from app.services import pronunciation, r2_storage  # noqa: F401
from app.services.pronunciation import (  # noqa: F401
    OUTPUT_FORMAT,
    TASK_NAME,
    VOICE_SETTINGS,
    error_kind,
    generate_audio,
    generation_fingerprint,
    is_configured,
)
from app.services.pronunciation_text import spoken_map_name  # noqa: F401


async def request_pronunciation(
    *, session: AsyncSession, map_obj: Map, force: bool = False
) -> MapPronunciation:
    return cast(
        MapPronunciation,
        await pronunciation.request_pronunciation(
            session=session, target=map_obj, force=force
        ),
    )


def public_pronunciation(
    *, map_obj: Map, row: MapPronunciation | None
) -> MapPronunciationPublic:
    return MapPronunciationPublic(
        **pronunciation.public_pronunciation(target=map_obj, row=row).model_dump()
    )


async def read_public_pronunciation(
    *, session: AsyncSession, map_obj: Map, row: MapPronunciation | None
) -> MapPronunciationPublic:
    return MapPronunciationPublic(
        **(
            await pronunciation.read_public_pronunciation(
                session=session, target=map_obj, row=row
            )
        ).model_dump()
    )


async def process_job(*, session: AsyncSession, row: MapPronunciation) -> None:
    await pronunciation.process_job(session=session, row=row, generate=generate_audio)


__all__ = [
    "TASK_NAME",
    "OUTPUT_FORMAT",
    "VOICE_SETTINGS",
    "error_kind",
    "generate_audio",
    "generation_fingerprint",
    "is_configured",
    "spoken_map_name",
    "request_pronunciation",
    "public_pronunciation",
    "read_public_pronunciation",
    "process_job",
]
