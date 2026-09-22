import pytest
from httpx import AsyncClient
from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models import ContentReaction
from tests.utils.utils import get_user_token_headers


async def _create_poll(client: AsyncClient, headers: dict[str, str]) -> dict:
    response = await client.post(
        f"{settings.API_V1_STR}/admin/polls",
        headers=headers,
        json={
            "title": "Reaction test poll",
            "options": [{"label": "Yes"}, {"label": "No"}],
        },
    )
    response.raise_for_status()
    return response.json()


@pytest.mark.asyncio
async def test_reaction_catalog_and_poll_reaction_lifecycle(
    client: AsyncClient,
    db: AsyncSession,
    superuser_token_headers: dict[str, str],
) -> None:
    catalog_response = await client.get(f"{settings.API_V1_STR}/reactions/emojis")
    assert catalog_response.status_code == 200
    assert [emoji["value"] for emoji in catalog_response.json()] == [
        "🔥",
        "👍",
        "❤️",
        "🎉",
        "🏆",
        "😂",
        "👀",
        "😮",
        "😢",
        "🤔",
        "💀",
        "👎",
    ]

    poll = await _create_poll(client, superuser_token_headers)
    user_headers = await get_user_token_headers(client)
    second_user_headers = await get_user_token_headers(client)
    target_url = f"{settings.API_V1_STR}/reactions/poll/{poll['id']}"

    first = await client.put(
        target_url,
        headers=user_headers,
        json={"emoji_key": "unicode:thumbs_up"},
    )
    assert first.status_code == 200
    assert first.json()["groups"][0]["reacted_by_me"] is True
    reaction_id = first.json()["groups"][0]["reaction_id"]
    stored_reaction = await db.get(ContentReaction, reaction_id)
    assert stored_reaction is not None
    assert stored_reaction.content_type == "poll"
    assert stored_reaction.content_id == poll["id"]

    duplicate = await client.put(
        target_url,
        headers=user_headers,
        json={"emoji_key": "unicode:thumbs_up"},
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["groups"][0]["count"] == 1

    multiple = await client.put(
        target_url,
        headers=user_headers,
        json={"emoji_key": "unicode:heart"},
    )
    assert multiple.status_code == 200
    assert {group["emoji"]["key"] for group in multiple.json()["groups"]} == {
        "unicode:thumbs_up",
        "unicode:heart",
    }

    anonymous_poll = await client.get(f"{settings.API_V1_STR}/polls/{poll['id']}")
    assert anonymous_poll.status_code == 200
    assert all(
        not group["reacted_by_me"]
        for group in anonymous_poll.json()["reactions"]["groups"]
    )

    reactors = await client.get(
        f"{target_url}/reactors",
        params={"emoji_key": "unicode:thumbs_up", "offset": 0, "limit": 1},
    )
    assert reactors.status_code == 200
    assert reactors.json()["count"] == 1
    assert len(reactors.json()["data"]) == 1
    assert "avatar_hash" in reactors.json()["data"][0]["player"]

    forbidden = await client.delete(
        f"{settings.API_V1_STR}/reactions/{reaction_id}",
        headers=second_user_headers,
    )
    assert forbidden.status_code == 404

    removed = await client.delete(
        f"{settings.API_V1_STR}/reactions/{reaction_id}", headers=user_headers
    )
    assert removed.status_code == 200
    assert {group["emoji"]["key"] for group in removed.json()["groups"]} == {
        "unicode:heart"
    }

    invalid = await client.put(
        target_url,
        headers=user_headers,
        json={"emoji_key": "discord:guild:emoji"},
    )
    assert invalid.status_code == 422

    deleted = await client.delete(
        f"{settings.API_V1_STR}/admin/polls/{poll['id']}",
        headers=superuser_token_headers,
    )
    assert deleted.status_code == 200
    remaining = (await db.exec(select(func.count()).select_from(ContentReaction))).one()
    assert remaining == 0

    deleted_target = await client.put(
        target_url,
        headers=user_headers,
        json={"emoji_key": "unicode:fire"},
    )
    assert deleted_target.status_code == 404


@pytest.mark.asyncio
async def test_reaction_rejects_bad_and_missing_target_ids(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    bad_id = await client.put(
        f"{settings.API_V1_STR}/reactions/poll/not-a-uuid",
        headers=normal_user_token_headers,
        json={"emoji_key": "unicode:fire"},
    )
    assert bad_id.status_code == 422

    missing = await client.put(
        f"{settings.API_V1_STR}/reactions/release/987654321",
        headers=normal_user_token_headers,
        json={"emoji_key": "unicode:fire"},
    )
    assert missing.status_code == 404
