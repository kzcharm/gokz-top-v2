from datetime import timedelta
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from httpx import AsyncClient
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
    PronunciationLanguage,
    PronunciationOptions,
    PronunciationRegenerate,
    PronunciationVoice,
)
from app.services import map_pronunciation_worker as worker
from app.services import pronunciation as service
from app.services.pronunciation_text import spoken_player_name


@pytest.fixture(autouse=True)
def configure(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in {
        "ELEVENLABS_API_KEY": "test-only",
        "R2_ACCOUNT_ID": "test-account",
        "R2_ACCESS_KEY_ID": "test-access",
        "R2_SECRET_ACCESS_KEY": "test-secret",
        "R2_BUCKET_NAME": "test-bucket",
        "R2_PUBLIC_BASE_URL": "https://audio.example.test",
    }.items():
        monkeypatch.setattr(settings, key, value)


@pytest.fixture
def options(monkeypatch: pytest.MonkeyPatch) -> PronunciationOptions:
    result = PronunciationOptions(
        voices=[
            PronunciationVoice(id=settings.ELEVENLABS_VOICE_ID, name="Lauren"),
            PronunciationVoice(id="jessica", name="Jessica"),
        ],
        languages=[
            PronunciationLanguage(code="en", name="English"),
            PronunciationLanguage(code="ja", name="Japanese"),
        ],
        default_voice_id=settings.ELEVENLABS_VOICE_ID,
    )
    monkeypatch.setattr(service, "get_options", AsyncMock(return_value=result))
    return result


@pytest_asyncio.fixture
async def player(db: AsyncSession) -> Player:
    player = Player(
        steamid64=76561198991700001,
        name="★ [AXE] 𝓐lpha_123 😊",
        custom_id="pronunciation-alpha",
    )
    db.add(player)
    await db.commit()
    return player


@pytest_asyncio.fixture
async def map_obj(db: AsyncSession) -> Map:
    row = Map(id=991710, name="kz_alouette_final_fix", validated=True)
    db.add(row)
    await db.commit()
    return row


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("★ [AXE] 𝓐lpha_123 😊", "AXE Alpha 123"),
        ("你好_世界", "你好 世界"),
        ("Саша", "Саша"),
        ("cafe\u0301", "café"),
        ("O’Neil-test", "O’Neil-test"),
        ("12345", "12345"),
        ("kz_player_final_fix", "kz player final fix"),
        ("🧑‍💻✨", ""),
        ("___ - '''", ""),
        ("76561198991700001", ""),
        ("a\u200bb", "a b"),
        ("1️⃣", "1"),
    ],
)
def test_name_cleanup(name: str, expected: str) -> None:
    assert spoken_player_name(name, 76561198991700001) == expected
    assert spoken_player_name(name, 0) == ""


@pytest.mark.asyncio
async def test_player_public_lazy_alias_rename_and_custom_id(
    client: AsyncClient, db: AsyncSession, player: Player
) -> None:
    url = "/v1/players/pronunciation-alpha/pronunciation"
    result = await client.get(url)
    assert result.status_code == 200 and result.json()["spoken_text"] == "AXE Alpha 123"
    assert result.json()["status"] == "missing"
    assert await db.get(PlayerPronunciation, player.steamid64) is None
    for _ in range(2):
        assert (await client.post(url)).status_code == 202
    row = await db.get(PlayerPronunciation, player.steamid64)
    assert row and row.attempts == 0
    row.status, row.object_key = "ready", "players/pronunciations/test.mp3"
    db.add(row)
    await db.commit()
    assert (await client.get(url)).json()["audio_url"].endswith("test.mp3")
    player.alias = "New_Alias"
    db.add(player)
    await db.commit()
    assert (await client.get(url)).json()["status"] == "missing"
    assert (await client.post(url)).json()["spoken_text"] == "New Alias"
    assert row.status == "pending" and row.object_key is None


@pytest.mark.asyncio
async def test_unreadable_and_unknown_players(
    client: AsyncClient,
    db: AsyncSession,
    player: Player,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    player.name = "✨😊"
    db.add(player)
    await db.commit()
    assert (await client.post(f"/v1/players/{player.steamid64}/pronunciation")).json()[
        "status"
    ] == "failed"
    assert (
        await client.post("/v1/players/missing-name/pronunciation")
    ).status_code == 404
    monkeypatch.setattr(settings, "ELEVENLABS_API_KEY", None)
    assert (
        await client.get(f"/v1/players/{player.steamid64}/pronunciation")
    ).status_code == 503


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["map", "player"])
@pytest.mark.usefixtures("options")
async def test_admin_overrides_persist_and_generate(
    client: AsyncClient,
    db: AsyncSession,
    player: Player,
    map_obj: Map,
    superuser_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:
    target = map_obj if kind == "map" else player
    route = (
        f"/v1/admin/maps/{map_obj.id}/pronunciation"
        if kind == "map"
        else f"/v1/admin/players/{player.steamid64}/pronunciation"
    )
    public_url = route.replace("/admin", "")
    current = await client.get(route, headers=superuser_token_headers)
    assert (
        current.status_code == 200
        and current.json()["voice_id"] == settings.ELEVENLABS_VOICE_ID
    )
    response = await client.post(
        f"{route}/regenerate",
        headers=superuser_token_headers,
        json={"text": "  Ah_lou ette  ", "voice_id": "jessica", "language_code": "ja"},
    )
    assert response.status_code == 202
    assert response.json()["spoken_text"] == "Ah lou ette"
    # Public input cannot override administrator corrections or change the model.
    response = await client.post(
        public_url, json={"text": "malicious", "model_id": "other", "voice_id": "other"}
    )
    assert response.json()["spoken_text"] == "Ah lou ette"
    model = MapPronunciation if kind == "map" else PlayerPronunciation
    identity = map_obj.id if kind == "map" else player.steamid64
    row = await db.get(model, identity)
    assert row and row.voice_override == "jessica" and row.language_code == "ja"
    generate = AsyncMock(return_value=b"mp3")
    monkeypatch.setattr(service, "generate_audio", generate)
    monkeypatch.setattr(service.r2_storage, "put_object", AsyncMock())
    await service.process_job(session=db, row=row)
    generate.assert_awaited_once_with(
        "Ah lou ette", voice_id="jessica", language_code="ja"
    )
    assert row.status == "ready" and row.object_key
    # A normal click keeps the approved clip and does not request another generation.
    assert (await client.post(public_url)).json()["status"] == "ready"
    target.name = "kz_changed_final" if kind == "map" else "Changed Player"
    db.add(target)
    await db.commit()
    assert (await client.get(public_url)).json()["status"] == "missing"
    assert (await client.post(public_url)).json()["status"] == "pending"
    assert (
        row.text_override is None
        and row.voice_override is None
        and row.language_code is None
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("roles", "map_allowed", "player_allowed"),
    [
        ([], False, False),
        (["server_owner"], False, False),
        (["map_admin"], True, False),
        (["admin"], True, True),
    ],
)
@pytest.mark.usefixtures("options")
async def test_admin_permissions(
    client: AsyncClient,
    player: Player,
    map_obj: Map,
    roles: list[str],
    map_allowed: bool,
    player_allowed: bool,
) -> None:
    auth = await client.post(
        "/v1/private/auth/session",
        json={
            "steamid64": "76561198991700002",
            "name": "Permission tester",
            "roles": roles,
            "is_active": True,
        },
    )
    headers = {"Authorization": f"Bearer {auth.json()['access_token']}"}
    payload = {
        "text": "test",
        "voice_id": settings.ELEVENLABS_VOICE_ID,
        "language_code": None,
    }
    for route, allowed in [
        (f"/v1/admin/maps/{map_obj.id}/pronunciation", map_allowed),
        (f"/v1/admin/players/{player.steamid64}/pronunciation", player_allowed),
    ]:
        assert (await client.get(route, headers=headers)).status_code == (
            200 if allowed else 403
        )
        assert (
            await client.post(route + "/regenerate", headers=headers, json=payload)
        ).status_code == (202 if allowed else 403)
    assert (
        await client.get("/v1/admin/pronunciations/options", headers=headers)
    ).status_code == (200 if map_allowed else 403)
    assert (
        await client.post(
            f"/v1/admin/players/{player.steamid64}/pronunciation/regenerate",
            json=payload,
        )
    ).status_code in {401, 403}


@pytest.mark.asyncio
@pytest.mark.usefixtures("options")
async def test_admin_validation_and_defaults(
    client: AsyncClient,
    db: AsyncSession,
    map_obj: Map,
    superuser_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    route = f"/v1/admin/maps/{map_obj.id}/pronunciation"
    payload = {"text": "hello", "voice_id": "jessica", "language_code": "en"}
    for changes in [
        {"text": "   "},
        {"text": "x" * 501},
        {"text": "bad\x00text"},
        {"voice_id": "missing"},
        {"language_code": "xx"},
        {"model_id": "other"},
    ]:
        response = await client.post(
            route + "/regenerate",
            headers=superuser_token_headers,
            json={**payload, **changes},
        )
        assert response.status_code == 422
    assert (
        await client.post(
            route + "/regenerate", headers=superuser_token_headers, json=payload
        )
    ).status_code == 202
    defaults = {
        "text": "alouette final",
        "voice_id": settings.ELEVENLABS_VOICE_ID,
        "language_code": None,
    }
    await client.post(
        route + "/regenerate", headers=superuser_token_headers, json=defaults
    )
    row = await db.get(MapPronunciation, map_obj.id)
    assert (
        row
        and row.text_override is None
        and row.voice_override is None
        and row.language_code is None
    )
    monkeypatch.setattr(
        service,
        "get_options",
        AsyncMock(side_effect=RuntimeError("private provider response")),
    )
    response = await client.get(
        "/v1/admin/pronunciations/options", headers=superuser_token_headers
    )
    assert (
        response.status_code == 503 and "private provider response" not in response.text
    )
    assert (
        await client.get(
            "/v1/admin/maps/999999999/pronunciation", headers=superuser_token_headers
        )
    ).status_code == 404


@pytest.mark.asyncio
async def test_shared_queue_fairness_and_pause(
    db: AsyncSession, player: Player, map_obj: Map, monkeypatch: pytest.MonkeyPatch
) -> None:
    map_row = await service.request_pronunciation(session=db, target=map_obj)
    player_row = await service.request_pronunciation(session=db, target=player)
    player_row.created_at = map_row.created_at - timedelta(seconds=1)
    db.add(player_row)
    await db.commit()
    generate = AsyncMock(return_value=b"mp3")
    monkeypatch.setattr(service, "generate_audio", generate)
    monkeypatch.setattr(service.r2_storage, "put_object", AsyncMock())
    assert await worker.process_next_job(session=db)
    assert player_row.status == "ready" and map_row.status == "pending"
    from app.services import map_pronunciation

    monkeypatch.setattr(map_pronunciation, "generate_audio", generate)
    assert await worker.process_next_job(session=db)
    assert map_row.status == "ready"
    player_row = await service.request_pronunciation(
        session=db, target=player, force=True
    )
    db.add(
        ScheduledTaskState(
            task_name=service.TASK_NAME, last_error="storage_credentials"
        )
    )
    await db.commit()
    assert not await worker.process_next_job(session=db)
    assert (
        await service.read_public_pronunciation(
            session=db, target=player, row=player_row
        )
    ).status == "failed"


@pytest.mark.asyncio
async def test_rename_during_generation_and_legacy_cache(
    db: AsyncSession, player: Player, map_obj: Map, monkeypatch: pytest.MonkeyPatch
) -> None:
    map_row = await service.request_pronunciation(session=db, target=map_obj)
    map_row.source_text = None  # A cached map generated before the override migration.
    map_row.status, map_row.object_key = "ready", "maps/pronunciations/legacy.mp3"
    db.add(map_row)
    await db.commit()
    assert service.public_pronunciation(target=map_obj, row=map_row).status == "ready"
    assert (
        await service.request_pronunciation(session=db, target=map_obj)
    ).status == "ready"
    row = await service.request_pronunciation(session=db, target=player)
    await db.commit()

    async def rename(_text: str) -> bytes:
        player.alias = "Different name"
        db.add(player)
        await db.commit()
        return b"old audio"

    monkeypatch.setattr(service.r2_storage, "put_object", AsyncMock())
    await service.process_job(session=db, row=row, generate=rename)
    assert row.status == "failed" and row.last_error == "name_changed"
    assert service.public_pronunciation(target=player, row=row).status == "missing"


@pytest.mark.asyncio
async def test_provider_choices_and_language_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_client = httpx.AsyncClient
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        if request.url.path == "/v1/models":
            return httpx.Response(
                200,
                json=[
                    {
                        "model_id": settings.ELEVENLABS_MODEL_ID,
                        "name": "Eleven v4",
                        "can_do_text_to_speech": True,
                        "languages": [{"language_id": "en", "name": "English"}],
                    }
                ],
            )
        if request.url.path == "/v2/voices":
            return httpx.Response(
                200,
                json={
                    "voices": [{"voice_id": "jessica", "name": "Jessica"}],
                    "has_more": False,
                    "total_count": 1,
                    "next_page_token": None,
                },
            )
        if request.url.path.endswith(settings.ELEVENLABS_VOICE_ID):
            return httpx.Response(
                200, json={"voice_id": settings.ELEVENLABS_VOICE_ID, "name": "Lauren"}
            )
        seen.append(json.loads(request.content))
        return httpx.Response(200, content=b"mp3")

    monkeypatch.setattr(service, "_options_cache", None)
    monkeypatch.setattr(
        service.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(
            transport=httpx.MockTransport(handler), **kwargs
        ),
    )
    choices = await service.get_options()
    assert len(choices.voices) == 2 and choices.languages[0].code == "en"
    assert await service.get_options() is choices
    await service.validate_overrides(
        PronunciationRegenerate(text="hello", voice_id="jessica", language_code="en")
    )
    assert (
        await service.generate_audio("hello", voice_id="jessica", language_code="en")
        == b"mp3"
    )
    assert (
        seen[0]["language_code"] == "en"
        and seen[0]["model_id"] == settings.ELEVENLABS_MODEL_ID
    )
