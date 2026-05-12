import pytest

from app.models.player_webhook import normalize_discord_webhook_url


def test_normalize_discord_webhook_url_keeps_discord_compatible_host() -> None:
    assert (
        normalize_discord_webhook_url(
            "https://qqbot.axekz.com/api/webhooks/188099455/"
            "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
        )
        == "https://qqbot.axekz.com/api/webhooks/188099455/"
        "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
    )


def test_normalize_discord_webhook_url_rejects_non_webhook_path() -> None:
    with pytest.raises(
        ValueError,
        match=(
            "Webhook URL must use the Discord-compatible "
            "/api/webhooks/<id>/<token> format"
        ),
    ):
        normalize_discord_webhook_url("https://example.com/not-a-discord-webhook")
