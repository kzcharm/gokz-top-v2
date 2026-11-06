from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from typing import Any

import jwt
import pytest
from fastapi.testclient import TestClient

from app.api.v1 import web_gokz
from app.core.config import settings
from app.core.security import ALGORITHM
from app.models import Player, User, get_datetime_utc
from app.web_gokz import app


class IdentitySession:
    async def get(self, model: Any, steamid: int) -> Any:
        if model is User:
            return User(steamid64=steamid, is_active=True)
        return Player(steamid64=steamid, name=f"Player {steamid}")


@asynccontextmanager
async def identity_session() -> AsyncIterator[IdentitySession]:
    yield IdentitySession()


def token(steamid: int) -> str:
    return jwt.encode(
        {
            "sub": str(steamid),
            "aud": "web-gokz",
            "exp": get_datetime_utc() + timedelta(hours=1),
        },
        settings.SECRET_KEY,
        algorithm=ALGORITHM,
    )


def test_socket_identity_chat_presence_and_rejection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "practice").mkdir()
    (tmp_path / "practice" / "kz_one.json").write_text('{"bspSha256":"v1"}')
    (tmp_path / "maps" / "kz_one").mkdir(parents=True)
    (tmp_path / "maps" / "kz_one" / "index.json").write_text("{}")
    monkeypatch.setattr(settings, "WEB_GOKZ_RESOURCES_DIR", tmp_path)
    monkeypatch.setattr(settings, "REPLAY_VIEWER_HOST", "http://localhost:5180")
    monkeypatch.setattr(web_gokz, "async_session_maker", identity_session)
    headers = {"origin": "http://localhost:5180"}
    with TestClient(app) as client:
        assert client.get("/v1/web-gokz/rooms").json()["count"] == 2
        with client.websocket_connect(
            "/v1/web-gokz/rooms/1/ws", headers=headers
        ) as first:
            first.send_json({"type": "auth", "token": token(1)})
            initial = first.receive_json()
            assert initial["room"]["players"][0]["name"] == "Player 1"
            with client.websocket_connect(
                "/v1/web-gokz/rooms/1/ws", headers=headers
            ) as second:
                second.send_json({"type": "auth", "token": token(2)})
                assert len(second.receive_json()["room"]["players"]) == 2
                assert len(first.receive_json()["room"]["players"]) == 2
                first.send_json({"type": "chat", "text": "Hello room"})
                chat = second.receive_json()
                assert chat["type"] == "chat" and chat["player"]["steamid64"] == "1"
                assert first.receive_json() == chat
                second.send_json(
                    {
                        "type": "state",
                        "generation": initial["room"]["generation"],
                        "position": [1, 2, 3],
                        "angles": [4, 5],
                        "mode": "KZT",
                        "crouched": False,
                        "timer_running": False,
                        "spectating": True,
                    }
                )
                spectator = first.receive_json()
                assert spectator["position"] == [1, 2, 3]
                assert spectator["spectating"] is True
                assert second.receive_json()["steamid64"] == "2"
                second.send_json({"type": "admin", "map_name": "kz_one"})
                assert second.receive_json()["type"] == "error"
            assert len(first.receive_json()["room"]["players"]) == 1
        with client.websocket_connect(
            "/v1/web-gokz/rooms/1/ws", headers=headers
        ) as bad:
            bad.send_json({"type": "auth", "token": "invalid"})
            assert bad.receive_json()["type"] == "error"
        with pytest.raises(Exception) as error:
            with client.websocket_connect(
                "/v1/web-gokz/rooms/1/ws",
                headers={"origin": "https://attacker.example"},
            ):
                pass
        assert getattr(error.value, "code", None) == 1008
