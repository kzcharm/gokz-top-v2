import uuid
from datetime import UTC, datetime


def get_datetime_utc() -> datetime:
    return datetime.now(UTC)


def generate_uuid7() -> uuid.UUID:
    return uuid.uuid7()
