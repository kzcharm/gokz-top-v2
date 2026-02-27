from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core.config import settings
from app.models import User


def test_create_auth_session(client: TestClient, db: Session) -> None:
    steamid64 = 76561199099999999
    response = client.post(
        f"{settings.API_V1_STR}/private/auth/session",
        json={
            "steamid64": steamid64,
            "is_superuser": False,
            "is_active": True,
            "name": "Pollo Listo",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert "access_token" in payload

    user = db.exec(select(User).where(User.steamid64 == steamid64)).first()
    assert user
