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

    admin_headers = await _token_headers(client, random_steamid64(), ["admin"])
    response = await client.get(
        f"{settings.API_V1_STR}/polls/{poll['id']}", headers=admin_headers
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["can_view_results"] is True
    assert [option["votes"] for option in payload["options"]] == [1, 0]


@pytest.mark.asyncio
async def test_admin_can_edit_and_add_but_not_delete_options_after_votes(
    client: AsyncClient,
) -> None:
    superuser_headers = await get_superuser_token_headers(client)
    create_response = await client.post(
        f"{settings.API_V1_STR}/admin/polls",
        headers=superuser_headers,
        json={
            "title": "Poll with a later deadline",
            "options": [
                {"label": "Yes"},
                {"label": "No"},
                {"label": "Maybe"},
            ],
        },
    )
    create_response.raise_for_status()
    poll = create_response.json()

    voter_headers = await _token_headers(client, random_steamid64(), [])
    vote_response = await client.post(
        f"{settings.API_V1_STR}/polls/{poll['id']}/votes",
        headers=voter_headers,
        json={"option_ids": [poll["options"][0]["id"]]},
    )
    vote_response.raise_for_status()

    end_date = "2030-01-02T03:04:00Z"
    update_response = await client.patch(
        f"{settings.API_V1_STR}/admin/polls/{poll['id']}",
        headers=superuser_headers,
        json={
            "ends_at": end_date,
            "options": [
                {
                    "label": "Definitely" if index == 0 else option["label"],
                    "description": option["description"],
                }
                for index, option in enumerate(poll["options"])
            ]
            + [{"label": "Ask me later", "description": None}],
        },
    )

    assert update_response.status_code == 200
    updated_poll = update_response.json()
    assert updated_poll["ends_at"] == "2030-01-02T03:04:00Z"
    assert [option["label"] for option in updated_poll["options"]] == [
        "Definitely",
        "No",
        "Maybe",
        "Ask me later",
    ]
    assert updated_poll["options"][0]["id"] == poll["options"][0]["id"]
    assert updated_poll["options"][0]["votes"] == 1

    delete_option_response = await client.patch(
        f"{settings.API_V1_STR}/admin/polls/{poll['id']}",
        headers=superuser_headers,
        json={
            "options": [
                {"label": option["label"], "description": option["description"]}
                for option in updated_poll["options"][:3]
            ]
        },
    )

    assert delete_option_response.status_code == 422
    assert (
        delete_option_response.json()["detail"]
        == "Poll options cannot be deleted after the first vote"
    )
