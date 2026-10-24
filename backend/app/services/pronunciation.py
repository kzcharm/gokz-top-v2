"""Shared durable name audio generation and administrator pronunciation overrides."""

import hashlib
import json
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import cast

import httpx
from elevenlabs import VoiceSettings
from elevenlabs.client import AsyncElevenLabs
from elevenlabs.core.api_error import ApiError
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models import (
    Map,
    MapPronunciation,
    Player,
    PlayerPronunciation,
    ScheduledTaskState,
)
from app.models.pronunciation import (
    PronunciationAdminPublic,
    PronunciationLanguage,
    PronunciationOptions,
    PronunciationPublic,
    PronunciationRegenerate,
    PronunciationStatus,
    PronunciationVoice,
)
from app.models.utils import generate_uuid7, get_datetime_utc
from app.services import r2_storage
from app.services.pronunciation_text import spoken_map_name, spoken_player_name

# Keep the existing persisted pause key and runner controls compatible.
TASK_NAME = "map_pronunciation"
OUTPUT_FORMAT = "mp3_44100_128"
VOICE_SETTINGS = {"stability": 0.5, "similarity_boost": 0.75, "clone_strength": 0.0}
logger = logging.getLogger(__name__)
Target = Map | Player
Job = MapPronunciation | PlayerPronunciation
_options_cache: tuple[float, str, str, PronunciationOptions] | None = None


def is_configured() -> bool:
    return bool(settings.ELEVENLABS_API_KEY and r2_storage.get_r2_storage_config())


def source_text(target: Target) -> str:
    if isinstance(target, Map):
        return spoken_map_name(target.name)
    return spoken_player_name(target.alias or target.name, target.steamid64)


def target_id(target: Target) -> int:
    return target.id if isinstance(target, Map) else target.steamid64


def job_id(row: Job) -> int:
    return row.map_id if isinstance(row, MapPronunciation) else row.steamid64


def generation_fingerprint(
    text: str, *, voice_id: str | None = None, language_code: str | None = None
) -> str:
    payload: dict[str, object] = {
        "text": text,
        "voice": voice_id or settings.ELEVENLABS_VOICE_ID,
        "model": settings.ELEVENLABS_MODEL_ID,
        "settings": VOICE_SETTINGS,
        "format": OUTPUT_FORMAT,
        "normalization": 1,
    }
    if language_code is not None:
        payload["language"] = language_code
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def matches_source(row: Job, text: str) -> bool:
    # Existing map rows predate the source_text column; preserve their cached clip.
    return (row.source_text if row.source_text is not None else row.spoken_text) == text


def effective_values(target: Target, row: Job | None) -> tuple[str, str, str | None]:
    source = source_text(target)
    if row is not None and matches_source(row, source):
        return (
            row.text_override or source,
            row.voice_override or settings.ELEVENLABS_VOICE_ID,
            row.language_code,
        )
    return source, settings.ELEVENLABS_VOICE_ID, None


async def request_pronunciation(
    *,
    session: AsyncSession,
    target: Target,
    force: bool = False,
    overrides: PronunciationRegenerate | None = None,
) -> Job:
    source = source_text(target)
    model = MapPronunciation if isinstance(target, Map) else PlayerPronunciation
    pk = "map_id" if isinstance(target, Map) else "steamid64"
    values = model(
        **{pk: target_id(target)},
        spoken_text=source,
        source_text=source,
        fingerprint=generation_fingerprint(source),
        status="pending" if source else "failed",
        last_error=None if source else "empty_spoken_name",
    ).model_dump()
    await session.exec(
        pg_insert(model).values(**values).on_conflict_do_nothing(index_elements=[pk])
    )
    row = cast(
        Job | None,
        await session.get(
            model, target_id(target), with_for_update=True, populate_existing=True
        ),
    )
    assert row is not None
    source_changed = not matches_source(row, source)
    if source_changed:
        row.text_override = row.voice_override = row.language_code = None
    if overrides is not None:
        row.text_override = overrides.text if overrides.text != source else None
        row.voice_override = (
            overrides.voice_id
            if overrides.voice_id != settings.ELEVENLABS_VOICE_ID
            else None
        )
        row.language_code = overrides.language_code
    row.source_text = source
    text, voice, language = effective_values(target, row)
    fingerprint = generation_fingerprint(text, voice_id=voice, language_code=language)
    if (
        source_changed
        or force
        or overrides is not None
        or row.fingerprint != fingerprint
    ):
        row.spoken_text = text
        row.fingerprint = fingerprint
        row.status = "pending" if text else "failed"
        row.object_key = None
        row.attempts = 0
        row.last_error = None if text else "empty_spoken_name"
        row.next_attempt_at = row.updated_at = get_datetime_utc()
    session.add(row)
    await session.flush()
    return row


def public_pronunciation(*, target: Target, row: Job | None) -> PronunciationPublic:
    text, voice, language = effective_values(target, row)
    if (
        row is None
        or not matches_source(row, source_text(target))
        or row.fingerprint
        != generation_fingerprint(text, voice_id=voice, language_code=language)
    ):
        return PronunciationPublic(
            status="missing" if text else "failed", spoken_text=text
        )
    return PronunciationPublic(
        status=cast(PronunciationStatus, row.status),
        spoken_text=text,
        audio_url=r2_storage.build_public_url(row.object_key)
        if row.status == "ready" and row.object_key
        else None,
    )


async def read_public_pronunciation(
    *, session: AsyncSession, target: Target, row: Job | None
) -> PronunciationPublic:
    result = public_pronunciation(target=target, row=row)
    if result.status in {"pending", "generating"}:
        state = await session.get(ScheduledTaskState, TASK_NAME)
        if state is not None and state.last_error:
            result.status = "failed"
    return result


async def admin_pronunciation(
    *, session: AsyncSession, target: Target, row: Job | None
) -> PronunciationAdminPublic:
    result = await read_public_pronunciation(session=session, target=target, row=row)
    _, voice, language = effective_values(target, row)
    return PronunciationAdminPublic(
        **result.model_dump(),
        source_text=source_text(target),
        voice_id=voice,
        language_code=language,
    )


async def generate_audio(
    text: str, *, voice_id: str | None = None, language_code: str | None = None
) -> bytes:
    async with httpx.AsyncClient(timeout=60.0) as http_client:
        client = AsyncElevenLabs(
            api_key=settings.ELEVENLABS_API_KEY, httpx_client=http_client
        )
        chunks = client.text_to_speech.convert(
            voice_id=voice_id or settings.ELEVENLABS_VOICE_ID,
            model_id=settings.ELEVENLABS_MODEL_ID,
            text=text,
            voice_settings=VoiceSettings.model_validate(VOICE_SETTINGS),
            language_code=language_code,
            output_format=OUTPUT_FORMAT,
            request_options={"max_retries": 0},
        )
        body = b"".join([chunk async for chunk in chunks])
    if not body:
        raise ValueError("empty_audio")
    return body


async def get_options() -> PronunciationOptions:
    global _options_cache
    # Do not cache keys or provider exception messages.
    cache_key = hashlib.sha256((settings.ELEVENLABS_API_KEY or "").encode()).hexdigest()
    config_key = f"{settings.ELEVENLABS_MODEL_ID}:{settings.ELEVENLABS_VOICE_ID}"
    if (
        _options_cache
        and time.monotonic() - _options_cache[0] < 600
        and _options_cache[1:3] == (cache_key, config_key)
    ):
        return _options_cache[3]
    async with httpx.AsyncClient(timeout=30.0) as http_client:
        client = AsyncElevenLabs(
            api_key=settings.ELEVENLABS_API_KEY, httpx_client=http_client
        )
        models = await client.models.list(request_options={"max_retries": 0})
        model = next(
            (
                m
                for m in models
                if m.model_id == settings.ELEVENLABS_MODEL_ID
                and m.can_do_text_to_speech
            ),
            None,
        )
        if model is None:
            raise ValueError("Configured speech model is unavailable")
        voices: dict[str, PronunciationVoice] = {}
        token: str | None = None
        while True:
            page = await client.voices.search(
                page_size=100, next_page_token=token, request_options={"max_retries": 0}
            )
            for voice in page.voices:
                voices[voice.voice_id] = PronunciationVoice(
                    id=voice.voice_id, name=voice.name or voice.voice_id
                )
            if (
                not page.has_more
                or not page.next_page_token
                or page.next_page_token == token
            ):
                break
            token = page.next_page_token
        if settings.ELEVENLABS_VOICE_ID not in voices:
            voice = await client.voices.get(
                settings.ELEVENLABS_VOICE_ID, request_options={"max_retries": 0}
            )
            voices[voice.voice_id] = PronunciationVoice(
                id=voice.voice_id, name=voice.name or voice.voice_id
            )
    result = PronunciationOptions(
        voices=sorted(voices.values(), key=lambda v: v.name.casefold()),
        languages=[
            PronunciationLanguage(code=language.language_id, name=language.name)
            for language in model.languages or []
        ],
        default_voice_id=settings.ELEVENLABS_VOICE_ID,
    )
    _options_cache = (time.monotonic(), cache_key, config_key, result)
    return result


async def validate_overrides(
    overrides: PronunciationRegenerate, options: PronunciationOptions | None = None
) -> None:
    options = options or await get_options()
    if overrides.voice_id not in {v.id for v in options.voices}:
        raise ValueError("Select an available voice")
    if overrides.language_code is not None and overrides.language_code not in {
        language.code for language in options.languages
    }:
        raise ValueError("Select a supported language")


def error_kind(error: Exception) -> tuple[str, bool, bool]:
    if isinstance(error, ApiError):
        status = error.status_code or 0
        quota = any(
            word in str(error.body).lower()
            for word in (
                "quota_exceeded",
                "insufficient_credits",
                "insufficient credits",
                "credit_balance",
            )
        )
        if status in {401, 402, 403} or quota:
            return "provider_credentials_or_credits", False, True
        return f"provider_http_{status}", status == 429 or status >= 500, False
    if isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code
        if status in {401, 403}:
            return "storage_credentials", False, True
        return f"storage_http_{status}", status == 429 or status >= 500, False
    return "generation_or_storage_failed", True, False


async def process_job(
    *,
    session: AsyncSession,
    row: Job,
    generate: Callable[..., Awaitable[bytes]] | None = None,
) -> None:
    generate = generate or generate_audio
    identity = job_id(row)
    model = type(row)
    target_model = Map if isinstance(row, MapPronunciation) else Player
    target = cast(Target | None, await session.get(target_model, identity))
    if target is None:
        return
    # A requested job uses the current name; ready/failed rows are never regenerated automatically.
    row = await request_pronunciation(session=session, target=target)
    if row.status not in {"pending", "generating"}:
        await session.commit()
        return
    if row.attempts >= settings.MAP_PRONUNCIATION_MAX_ATTEMPTS:
        row.status, row.last_error = "failed", "retry_limit_reached"
        session.add(row)
        await session.commit()
        return
    fingerprint = row.fingerprint
    row.status = "generating"
    row.attempts += 1
    row.updated_at = get_datetime_utc()
    started_at = row.updated_at
    text = row.spoken_text
    voice, language = row.voice_override, row.language_code
    session.add(row)
    await session.commit()
    try:
        body = (
            await generate(text, voice_id=voice, language_code=language)
            if voice or language
            else await generate(text)
        )
        namespace = "maps" if target_model is Map else "players"
        key = f"{namespace}/pronunciations/{identity}/{fingerprint}/{generate_uuid7()}.mp3"
        await r2_storage.put_object(
            key=key,
            body=body,
            content_type="audio/mpeg",
            cache_control="public, max-age=31536000, immutable",
        )
        current = cast(
            Job | None,
            await session.get(
                model, identity, with_for_update=True, populate_existing=True
            ),
        )
        target = cast(
            Target | None,
            await session.get(target_model, identity, populate_existing=True),
        )
        if (
            current is None
            or current.fingerprint != fingerprint
            or current.updated_at != started_at
        ):
            await session.rollback()
            return
        row = current
        if target is None or not matches_source(row, source_text(target)):
            row.status, row.last_error = "failed", "name_changed"
        else:
            row.object_key, row.status, row.last_error = key, "ready", None
    except Exception as error:
        code, retryable, pause = error_kind(error)
        await session.rollback()
        current = cast(
            Job | None,
            await session.get(
                model, identity, with_for_update=True, populate_existing=True
            ),
        )
        if (
            current is None
            or current.fingerprint != fingerprint
            or current.updated_at != started_at
        ):
            await session.rollback()
            return
        row = current
        row.last_error = code
        row.status = (
            "pending"
            if pause
            or (retryable and row.attempts < settings.MAP_PRONUNCIATION_MAX_ATTEMPTS)
            else "failed"
        )
        row.next_attempt_at = get_datetime_utc() + timedelta(
            seconds=min(3600, 30 * 2 ** min(row.attempts, 7))
        )
        if pause:
            state = await session.get(
                ScheduledTaskState, TASK_NAME
            ) or ScheduledTaskState(task_name=TASK_NAME)
            state.last_error = code
            session.add(state)
            logger.error(
                "Pronunciation queue paused (%s); fix configuration or credits, then resume the pronunciation worker",
                code,
            )
    row.updated_at = get_datetime_utc()
    session.add(row)
    await session.commit()
