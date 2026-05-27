import uuid
from datetime import UTC, datetime
from secrets import randbits
from typing import Any

from pydantic import model_validator
from sqlmodel import SQLModel


def get_datetime_utc() -> datetime:
    return datetime.now(UTC)


def generate_uuid7(*, timestamp: datetime | None = None) -> uuid.UUID:
    if timestamp is None:
        return uuid.uuid7()

    normalized = timestamp.astimezone(UTC) if timestamp.tzinfo else timestamp.replace(
        tzinfo=UTC
    )
    unix_ts_ms = int(normalized.timestamp() * 1000)
    if unix_ts_ms < 0 or unix_ts_ms >= 1 << 48:
        raise ValueError("UUIDv7 timestamp must fit in 48 bits")

    rand_a = randbits(12)
    rand_b = randbits(62)
    value = (
        (unix_ts_ms << 80)
        | (0x7 << 76)
        | (rand_a << 64)
        | (0b10 << 62)
        | rand_b
    )
    return uuid.UUID(int=value)


class LegacyDatetimeNamesMixin(SQLModel):
    def __init__(self, /, **data: Any) -> None:
        super().__init__(**self._normalize_legacy_datetime_keys(data))

    @model_validator(mode="before")
    @classmethod
    def _normalize_legacy_datetime_keys(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        normalized = dict(data)
        if "created_at" not in normalized and "created_on" in normalized:
            normalized["created_at"] = normalized.pop("created_on")
        if "updated_at" not in normalized and "updated_on" in normalized:
            normalized["updated_at"] = normalized.pop("updated_on")
        if "expires_at" not in normalized and "expires_on" in normalized:
            normalized["expires_at"] = normalized.pop("expires_on")
        return normalized
