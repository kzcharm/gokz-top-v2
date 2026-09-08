import pytest
from httpx import AsyncClient

from app.core.config import settings
from tests.utils.utils import get_superuser_token_headers, random_steamid64


async def _token_headers(
    client: AsyncClient, steamid64: int, roles: list[str]
) -> dict[str, str]:
    response = await client.post(
        f"{settings.API_V1_STR}/private/auth/session",
        json={
            "steamid64": steamid64,
            "roles": roles,
            "is_active": True,
            "name": "Poll Test User",
        },
    )
    response.raise_for_status()
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.mark.asyncio
async def test_admin_can_view_active_poll_results_before_voting(
    client: AsyncClient,
) -> None:
    superuser_headers = await get_superuser_token_headers(client)
    create_response = await client.post(
        f"{settings.API_V1_STR}/admin/polls",
        headers=superuser_headers,
        json={
            "title": "Admin results visibility",
            "options": [{"label": "Yes"}, {"label": "No"}],
        },
    )
    create_response.raise_for_status()
    poll = create_response.json()
    option_ids = [option["id"] for option in poll["options"]]

    voter_headers = await _token_headers(client, random_steamid64(), [])
    vote_response = await client.post(
        f"{settings.API_V1_STR}/polls/{poll['id']}/votes",
        headers=voter_headers,
        json={"option_ids": [option_ids[0]]},
    )
    vote_response.raise_for_status()

    admin_headers = await _token_headers(
        client, random_steamid64(), ["admin"]
    )
    response = await client.get(
        f"{settings.API_V1_STR}/polls/{poll['id']}", headers=admin_headers
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["can_view_results"] is True
    assert [option["votes"] for option in payload["options"]] == [1, 0]
