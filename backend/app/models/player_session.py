import uuid
from datetime import UTC, datetime
from ipaddress import IPv4Address

from pydantic import field_validator
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    Computed,
    DateTime,
    Index,
    Integer,
    text,
)
from sqlalchemy.dialects.postgresql import INET
from sqlmodel import Field, SQLModel


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _validate_uuid7(value: uuid.UUID) -> uuid.UUID:
    if value.version != 7:
        raise ValueError("session_id must be a UUIDv7")
    return value


def _parse_steamid64(value: str) -> int:
    normalized = value.strip()
    if not normalized.isdigit():
        raise ValueError("player_steamid64 must be an integer-compatible string")
    return int(normalized)


class PlayerSession(SQLModel, table=True):
    __tablename__ = "player_session"
    __table_args__ = (
        CheckConstraint("family(ip_address) = 4", name="ck_player_session_ipv4"),
        CheckConstraint(
            "disconnect_at IS NULL OR disconnect_at >= connected_at",
            name="ck_player_session_disconnect_after_connect",
        ),
        CheckConstraint(
            "last_heartbeat_at >= connected_at",
            name="ck_player_session_heartbeat_after_connect",
        ),
        Index(
            "ix_player_session_open_timeout",
            "last_heartbeat_at",
            postgresql_where=text("disconnect_at IS NULL"),
        ),
        Index(
            "ix_player_session_player_connected_at",
            "player_steamid64",
            text("connected_at DESC"),
        ),
        Index(
            "ix_player_session_group_last_heartbeat_at",
            "server_group_id",
            text("last_heartbeat_at DESC"),
        ),
        Index(
            "ix_player_session_group_map_connected_at",
            "server_group_id",
            "map_name",
            text("connected_at DESC"),
        ),
        Index(
            "ix_player_session_ip_connected_at",
            "ip_address",
            text("connected_at DESC"),
        ),
    )

    id: uuid.UUID = Field(primary_key=True)
    player_steamid64: int = Field(
        foreign_key="player.steamid64",
        nullable=False,
        ondelete="CASCADE",
        sa_type=BigInteger,
    )
    server_group_id: uuid.UUID = Field(
        foreign_key="server_group.id",
        nullable=False,
    )
    connected_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    disconnect_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    last_heartbeat_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    ip_address: str = Field(
        sa_column=Column(INET, nullable=False),
    )
    map_name: str = Field(min_length=1, max_length=255)
    duration_seconds: int | None = Field(
        default=None,
        sa_column=Column(
            Integer,
            Computed(
                "EXTRACT(EPOCH FROM (disconnect_at - connected_at))::INTEGER",
                persisted=True,
            ),
        ),
    )


class PlayerSessionConnect(SQLModel):
    session_id: uuid.UUID
    player_steamid64: str
    connected_at: datetime
    ip_address: IPv4Address
    map_name: str = Field(min_length=1, max_length=255)

    @field_validator("session_id")
    @classmethod
    def _validate_session_id(cls, value: uuid.UUID) -> uuid.UUID:
        return _validate_uuid7(value)

    @field_validator("player_steamid64")
    @classmethod
    def _validate_player_steamid64(cls, value: str) -> str:
        return str(_parse_steamid64(value))

    @field_validator("connected_at")
    @classmethod
    def _normalize_connected_at(cls, value: datetime) -> datetime:
        return _normalize_datetime(value)

    @field_validator("map_name")
    @classmethod
    def _normalize_map_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("map_name must not be blank")
        return normalized


class PlayerSessionHeartbeat(SQLModel):
    session_id: uuid.UUID
    heartbeat_at: datetime

    @field_validator("session_id")
    @classmethod
    def _validate_session_id(cls, value: uuid.UUID) -> uuid.UUID:
        return _validate_uuid7(value)

    @field_validator("heartbeat_at")
    @classmethod
    def _normalize_heartbeat_at(cls, value: datetime) -> datetime:
        return _normalize_datetime(value)


class PlayerSessionDisconnect(SQLModel):
    session_id: uuid.UUID
    disconnect_at: datetime

    @field_validator("session_id")
    @classmethod
    def _validate_session_id(cls, value: uuid.UUID) -> uuid.UUID:
        return _validate_uuid7(value)

    @field_validator("disconnect_at")
    @classmethod
    def _normalize_disconnect_at(cls, value: datetime) -> datetime:
        return _normalize_datetime(value)


class PlayerSessionPublic(SQLModel):
    id: uuid.UUID
    player_steamid64: str
    server_group_id: uuid.UUID
    connected_at: datetime
    disconnect_at: datetime | None = None
    last_heartbeat_at: datetime
    ip_address: str
    map_name: str
    duration_seconds: int | None = None


__all__ = [
    "PlayerSession",
    "PlayerSessionConnect",
    "PlayerSessionDisconnect",
    "PlayerSessionHeartbeat",
    "PlayerSessionPublic",
]
