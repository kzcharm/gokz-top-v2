import uuid
from datetime import UTC, datetime
from secrets import randbits
from typing import Any, cast

from pydantic import model_validator
from sqlalchemy import Row, SQLColumnExpression, Table, inspect
from sqlalchemy.sql.selectable import FromClause
from sqlmodel import SQLModel
from sqlmodel.sql.expression import Select


def get_sqlmodel_table(model: type[SQLModel]) -> Table:
    """Expose SQLModel's runtime table through SQLAlchemy's typed inspection API."""
    return cast(Table, inspect(model, raiseerr=True).local_table)


def select_row(
    *entities: SQLColumnExpression[Any] | type[SQLModel] | FromClause,
) -> Select[Row[tuple[Any, ...]]]:
    """Select a row beyond the four columns in SQLModel's select overloads."""
    return Select(*entities)


def get_datetime_utc() -> datetime:
    return datetime.now(UTC)


def generate_uuid7(*, timestamp: datetime | None = None) -> uuid.UUID:
    if timestamp is None:
        return uuid.uuid7()

    normalized = (
        timestamp.astimezone(UTC) if timestamp.tzinfo else timestamp.replace(tzinfo=UTC)
    )
    unix_ts_ms = int(normalized.timestamp() * 1000)
    if unix_ts_ms < 0 or unix_ts_ms >= 1 << 48:
        raise ValueError("UUIDv7 timestamp must fit in 48 bits")

    rand_a = randbits(12)
    rand_b = randbits(62)
    value = (unix_ts_ms << 80) | (0x7 << 76) | (rand_a << 64) | (0b10 << 62) | rand_b
    return uuid.UUID(int=value)


class LegacyDatetimeNamesMixin(SQLModel):
    def __init__(self, /, **data: Any) -> None:
        super().__init__(**normalize_legacy_datetime_keys(data))

    @model_validator(mode="before")
    @classmethod
    def _normalize_legacy_datetime_keys(cls, data: Any) -> Any:
        return normalize_legacy_datetime_keys(data)


def normalize_legacy_datetime_keys(data: Any) -> Any:
    if not isinstance(data, dict):
        return data

    normalized = dict(data)
    for old_key, new_key in (
        ("created_on", "created_at"),
        ("updated_on", "updated_at"),
        ("expires_on", "expires_at"),
    ):
        if new_key not in normalized and old_key in normalized:
            normalized[new_key] = normalized.pop(old_key)
    return normalized
