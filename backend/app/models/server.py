import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict
from sqlalchemy import BigInteger, DateTime, Index, PrimaryKeyConstraint
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Column, Field, Relationship, SQLModel

from .utils import generate_uuid7, get_datetime_utc


def _enum_values(enum_class: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_class]


class ServerSource(StrEnum):
    MANUAL = "manual"
    STEAM_MASTER = "steam_master"


class ServerStatus(StrEnum):
    ENABLED = "enabled"
    INVALID = "invalid"
    DISABLED = "disabled"


class ServerHeartbeatSource(StrEnum):
    PLUGIN = "plugin"
    A2S = "a2s"
    OFFLINE_MARK = "offline_mark"


class ServerGroupStatus(StrEnum):
    PENDING = "pending"
    VALIDATED = "validated"
    INVALIDATED = "invalidated"


class ServerGroupBase(SQLModel):
    name: str = Field(min_length=1, max_length=255)


class ServerGroupCreate(ServerGroupBase):
    pass


class ServerGroupUpdate(SQLModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    status: ServerGroupStatus | None = None


class ServerGroup(ServerGroupBase, table=True):
    __tablename__ = "server_group"  # type: ignore[assignment]
    __table_args__ = (
        Index("uq_server_group_name", "name", unique=True),
        Index("uq_server_group_api_key", "api_key", unique=True),
    )

    id: uuid.UUID = Field(default_factory=generate_uuid7, primary_key=True)
    api_key: str = Field(max_length=36)
    owner_steamid64: int | None = Field(
        default=None,
        foreign_key="user.steamid64",
        sa_type=BigInteger,
    )
    status: ServerGroupStatus = Field(
        default=ServerGroupStatus.PENDING,
        sa_column=Column(
            SQLAlchemyEnum(
                ServerGroupStatus,
                name="server_group_status",
                values_callable=_enum_values,
            ),
            nullable=False,
        ),
    )
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore[arg-type]
    )
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore[arg-type]
    )
    servers: list["Server"] = Relationship(back_populates="group")  # noqa: UP037
    globalapi_servers: list["ServerGlobalapi"] = Relationship(  # noqa: F821, UP037
        back_populates="group"
    )


class ServerBase(SQLModel):
    ip: str = Field(min_length=1, max_length=64)
    port: int = Field(ge=1, le=65535)
    status: ServerStatus = ServerStatus.ENABLED
    country: str | None = Field(default=None, max_length=2)
    city: str | None = Field(default=None, max_length=255)


class ServerCreate(SQLModel):
    group_id: uuid.UUID | None = None
    ip: str = Field(min_length=1, max_length=64)
    port: int = Field(ge=1, le=65535)
    status: ServerStatus = ServerStatus.ENABLED
    country: str | None = Field(default=None, max_length=2)
    city: str | None = Field(default=None, max_length=255)


class ServerUpdate(SQLModel):
    group_id: uuid.UUID | None = None
    ip: str | None = Field(default=None, min_length=1, max_length=64)
    port: int | None = Field(default=None, ge=1, le=65535)
    status: ServerStatus | None = None
    country: str | None = Field(default=None, max_length=2)
    city: str | None = Field(default=None, max_length=255)


class Server(ServerBase, table=True):
    __tablename__ = "server"  # type: ignore[assignment]
    __table_args__ = (
        Index("ix_server_group_id", "group_id"),
        Index("ix_server_status", "status"),
        Index("uq_server_ip_port", "ip", "port", unique=True),
    )

    id: uuid.UUID = Field(default_factory=generate_uuid7, primary_key=True)
    group_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="server_group.id",
        ondelete="SET NULL",
    )
    status: ServerStatus = Field(
        default=ServerStatus.ENABLED,
        sa_column=Column(
            SQLAlchemyEnum(
                ServerStatus,
                name="server_status",
                values_callable=_enum_values,
            ),
            nullable=False,
        ),
    )
    source: dict[str, Any] = Field(
        default_factory=lambda: {"type": ServerSource.MANUAL.value},
        sa_column=Column(JSONB, nullable=False),
    )
    last_discovered_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # type: ignore[arg-type]
    )
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore[arg-type]
    )
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore[arg-type]
    )

    group: ServerGroup | None = Relationship(back_populates="servers")
    live_status: Optional["ServerLiveStatus"] = Relationship(  # noqa: UP045, UP037
        back_populates="server",
        sa_relationship_kwargs={"uselist": False},
    )


class ServerLiveStatusBase(SQLModel):
    hostname: str | None = Field(default=None, max_length=255)
    map: str | None = Field(default=None, max_length=255)
    player_count: int = Field(default=0, ge=0)
    max_players: int = Field(default=0, ge=0)
    players: list[dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False),
    )
    is_online: bool = False
    last_plugin_seen_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # type: ignore[arg-type]
    )
    last_a2s_seen_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # type: ignore[arg-type]
    )
    last_successful_seen_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # type: ignore[arg-type]
    )
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore[arg-type]
    )


class ServerLiveStatus(ServerLiveStatusBase, table=True):
    __tablename__ = "server_live_status"  # type: ignore[assignment]
    __table_args__ = (
        Index("ix_server_live_status_is_online", "is_online"),
        Index("ix_server_live_status_last_plugin_seen_at", "last_plugin_seen_at"),
        Index("ix_server_live_status_last_a2s_seen_at", "last_a2s_seen_at"),
    )

    server_id: uuid.UUID = Field(
        foreign_key="server.id",
        primary_key=True,
        ondelete="CASCADE",
    )
    server: Server = Relationship(back_populates="live_status")


class ServerHeartbeatRaw(SQLModel, table=True):
    __tablename__ = "server_heartbeat_raw"  # type: ignore[assignment]
    __table_args__ = (
        PrimaryKeyConstraint(
            "observed_at",
            "id",
            name="pk_server_heartbeat_raw",
        ),
        Index(
            "ix_server_heartbeat_raw_server_id_observed_at",
            "server_id",
            "observed_at",
        ),
        {"postgresql_partition_by": "RANGE (observed_at)"},
    )

    id: uuid.UUID = Field(default_factory=generate_uuid7)
    server_id: uuid.UUID = Field(
        foreign_key="server.id",
        nullable=False,
        ondelete="CASCADE",
    )
    source: ServerHeartbeatSource = Field(
        sa_column=Column(
            SQLAlchemyEnum(
                ServerHeartbeatSource,
                name="server_heartbeat_source",
                values_callable=_enum_values,
            ),
            nullable=False,
        ),
    )
    observed_at: datetime = Field(
        sa_type=DateTime(timezone=True),  # type: ignore[arg-type]
    )
    hostname: str | None = Field(default=None, max_length=255)
    map: str | None = Field(default=None, max_length=255)
    player_count: int = Field(default=0, ge=0)
    max_players: int = Field(default=0, ge=0)
    players: list[dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False),
    )
    is_online: bool = False


class ServerGroupSummary(SQLModel):
    id: uuid.UUID
    name: str


class ServerLiveStatusPublic(ServerLiveStatusBase):
    pass


class ServerPublic(ServerBase):
    id: uuid.UUID
    group_id: uuid.UUID | None = None
    region: str | None = None
    source: dict[str, Any]
    last_discovered_at: datetime | None = None
    map_tier: int | None = None
    created_at: datetime
    updated_at: datetime
    group: ServerGroupSummary | None = None
    live_status: ServerLiveStatusPublic | None = None


class ServersPublic(SQLModel):
    data: list[ServerPublic]
    count: int


class ServerGroupPublic(ServerGroupBase):
    id: uuid.UUID
    owner_steamid64: str | None = None
    status: ServerGroupStatus
    server_count: int = 0
    created_at: datetime
    updated_at: datetime


class ServerGroupsPublic(SQLModel):
    data: list[ServerGroupPublic]
    count: int


class ServerGroupApiKeyPublic(SQLModel):
    group: ServerGroupPublic
    api_key: str


class ServerListQuery(SQLModel):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=1000)
    online: bool | None = None
    group_id: uuid.UUID | None = None
    country: str | None = Field(default=None, max_length=2)
    region: str | None = Field(default=None, max_length=3)
    city: str | None = Field(default=None, max_length=255)
    source_type: ServerSource | None = None


class ServerHistoryQuery(SQLModel):
    from_at: datetime | None = None
    to_at: datetime | None = None
    bucket_seconds: int = Field(default=60, ge=1, le=86_400)


class ServerHistoryBucketPublic(SQLModel):
    bucket_start: datetime
    heartbeat_count: int
    hostname: str | None = None
    map: str | None = None
    player_count: int
    max_players: int
    players: list[dict[str, Any]] = Field(default_factory=list)
    is_online: bool


class ServerHistoryPublic(SQLModel):
    data: list[ServerHistoryBucketPublic]
    count: int


class ServerDiscoveryRunPublic(SQLModel):
    started_at: datetime
    completed_at: datetime
    regions_scanned: int
    candidate_count: int
    upserted_count: int


class ServerStatusPut(SQLModel):
    ip: str = Field(min_length=1, max_length=64)
    port: int = Field(ge=1, le=65535)
    observed_at: datetime
    hostname: str = Field(min_length=1, max_length=255)
    map: str = Field(min_length=1, max_length=255)
    player_count: int = Field(ge=0)
    max_players: int = Field(ge=0)
    players: list[dict[str, Any]] = Field(default_factory=list)


class ServerUpdateEvent(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "type": "server.updated",
                "server": {
                    "id": "019ce276-b619-7716-8092-7dd7f88d7d6b",
                    "ip": "127.0.0.1",
                    "port": 27015,
                },
            }
        }
    )

    type: str
    server: ServerPublic


class ServerSnapshotEvent(SQLModel):
    type: str
    servers: list[ServerPublic]


__all__ = [
    "Server",
    "ServerBase",
    "ServerCreate",
    "ServerGroup",
    "ServerGroupApiKeyPublic",
    "ServerGroupBase",
    "ServerGroupCreate",
    "ServerGroupPublic",
    "ServerGroupSummary",
    "ServerGroupUpdate",
    "ServerDiscoveryRunPublic",
    "ServerGroupsPublic",
    "ServerHeartbeatRaw",
    "ServerHeartbeatSource",
    "ServerHistoryBucketPublic",
    "ServerHistoryPublic",
    "ServerHistoryQuery",
    "ServerListQuery",
    "ServerLiveStatus",
    "ServerLiveStatusBase",
    "ServerLiveStatusPublic",
    "ServerPublic",
    "ServerSnapshotEvent",
    "ServersPublic",
    "ServerStatus",
    "ServerSource",
    "ServerStatusPut",
    "ServerUpdate",
    "ServerUpdateEvent",
]
