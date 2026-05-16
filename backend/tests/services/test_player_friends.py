from datetime import UTC, datetime, timedelta

from app.services import player_friends


def test_format_friends_sync_retry_wait_uses_largest_rounded_up_minute_unit() -> None:
    now = datetime(2026, 5, 14, 12, 0, 0, tzinfo=UTC)

    assert (
        player_friends.format_friends_sync_retry_wait(
            now=now,
            next_allowed_at=now + timedelta(minutes=52, seconds=1),
        )
        == "53 minutes"
    )


def test_format_friends_sync_retry_wait_uses_largest_rounded_up_hour_unit() -> None:
    now = datetime(2026, 5, 14, 12, 0, 0, tzinfo=UTC)

    assert (
        player_friends.format_friends_sync_retry_wait(
            now=now,
            next_allowed_at=now + timedelta(hours=11, minutes=1),
        )
        == "12 hours"
    )


def test_format_friends_sync_retry_wait_uses_largest_rounded_up_day_unit() -> None:
    now = datetime(2026, 5, 14, 12, 0, 0, tzinfo=UTC)

    assert (
        player_friends.format_friends_sync_retry_wait(
            now=now,
            next_allowed_at=now + timedelta(days=1, hours=2),
        )
        == "2 days"
    )
