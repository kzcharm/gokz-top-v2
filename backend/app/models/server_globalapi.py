import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index
from sqlmodel import Field, Relationship, SQLModel

from .utils import LegacyDatetimeNamesMixin, get_datetime_utc


class ServerGlobalapiBase(LegacyDatetimeNamesMixin):
    port: int = Field(default=27015, ge=1, le=65535)
    ip: str | None = Field(default=None, max_length=255)
    name: str | None = Field(default=None, max_length=255)
    owner_steamid64: int = Field(default=0, sa_type=BigInteger)
    approval_status: int = Field(default=0, ge=0, le=1)
    approved_by_steamid64: int = Field(default=0, sa_type=BigInteger)
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        validation_alias="created_on",
        sa_type=DateTime(timezone=True),  # type: ignore[arg-type]
    )
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        validation_alias="updated_on",
        sa_type=DateTime(timezone=True),  # type: ignore[arg-type]
    )
    synced_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore[arg-type]
    )


class ServerGlobalapi(ServerGlobalapiBase, table=True):
    __tablename__ = "server_globalapi"  # type: ignore[assignment]
    __table_args__ = (
        Index("ix_server_globalapi_group_id", "group_id"),
        Index("ix_server_globalapi_name", "name"),
        Index("ix_server_globalapi_owner_steamid64", "owner_steamid64"),
        Index("ix_server_globalapi_approval_status", "approval_status"),
    )

    id: int = Field(primary_key=True)
    group_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="server_group.id",
        ondelete="SET NULL",
    )

    group: "ServerGroup" = Relationship(  # noqa: F821, UP037
        back_populates="globalapi_servers"
    )


class ServerGlobalapiCompatPublicV0(SQLModel):
    id: int
    port: int
    ip: str | None = None
    name: str | None = None
    owner_steamid64: str


class ServerGlobalapiListQuery(SQLModel):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=10000)
    id: list[int] | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    ip: str | None = Field(default=None, max_length=255)
    name: str | None = Field(default=None, max_length=255)
    owner_steamid64: int | None = Field(default=None, sa_type=BigInteger)
    approval_status: int | None = Field(default=None, ge=0, le=1)
