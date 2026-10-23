"""Durable identities and upload receipts for server-originated records."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import UUID7, AwareDatetime, BaseModel, ConfigDict
from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    Index,
    UniqueConstraint,
    text,
)
from sqlmodel import Field, SQLModel, col

from .record import KZMode
from .utils import generate_uuid7, get_datetime_utc


class RecordUploadReceipt(SQLModel, table=True):
    __tablename__ = "record_upload_receipt"
    __table_args__ = (UniqueConstraint("server_id", "idempotency_key"),)

    id: uuid.UUID = Field(default_factory=generate_uuid7, primary_key=True)
    server_id: uuid.UUID = Field(foreign_key="server.id", index=True)
    idempotency_key: str = Field(max_length=128)
    record_uuid: uuid.UUID = Field(foreign_key="record.uuid", index=True)
    payload_hash: str = Field(max_length=64)
    payload: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    result: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    replay_eligible: bool = False
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class RecordUuidAlias(SQLModel, table=True):
    __tablename__ = "record_uuid_alias"
    alias: uuid.UUID = Field(primary_key=True)
    record_uuid: uuid.UUID = Field(foreign_key="record.uuid", index=True)


class RecordSourceClaim(SQLModel, table=True):
    __tablename__ = "record_source_claim"
    __table_args__ = (
        UniqueConstraint("record_uuid", "globalapi_id"),
        Index(
            "ux_record_source_claim_verified_globalapi",
            "globalapi_id",
            unique=True,
            postgresql_where=text("state = 'verified'"),
        ),
    )
    id: uuid.UUID = Field(default_factory=generate_uuid7, primary_key=True)
    record_uuid: uuid.UUID = Field(foreign_key="record.uuid", index=True)
    globalapi_id: int = Field(sa_type=BigInteger, index=True)
    state: str = Field(default="pending", max_length=32, index=True)
    detail: str = Field(default="", max_length=1024)
    source_payload: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class RecordReplay(SQLModel, table=True):
    __tablename__ = "record_replay"
    __table_args__ = (
        CheckConstraint("storage IN ('disk', 'r2')", name="ck_record_replay_storage"),
        CheckConstraint("size > 0", name="ck_record_replay_size"),
    )
    record_uuid: uuid.UUID = Field(foreign_key="record.uuid", primary_key=True)
    storage: str = Field(max_length=8)
    key: str = Field(max_length=1024)
    available: bool = Field(default=True, index=True)
    checksum: str = Field(max_length=64)
    size: int = Field(sa_type=BigInteger)
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    checked_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class RecordIntegrity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fresh_map: bool
    server_settings: bool
    client_settings: bool
    required_plugins: bool
    timer_valid: bool
    mode_stable: bool
    anticheat_clear: bool

    @property
    def valid(self) -> bool:
        return all(self.model_dump().values())


class RecordCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")
    server_id: uuid.UUID
    map_name: str = Field(min_length=1, max_length=255)
    bsp_size: int = Field(gt=0)
    stage: int = Field(default=0, ge=0, le=255)
    mode: KZMode
    mode_version: int = Field(gt=0)
    steamid64: int = Field(ge=76561197960265728, le=76561202255233023)
    style: int = Field(default=0, ge=0, le=0)
    tickrate: int = Field(default=128, ge=128, le=128)
    integrity: RecordIntegrity


class RecordFinish(RecordCheck):
    record_uuid: UUID7 | None = None
    time: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    teleports: int = Field(ge=0)
    finished_at: AwareDatetime


class GlobalApiClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    globalapi_id: int = Field(gt=0)


def install_record_read_properties() -> None:
    """Indexed correlated metadata reads, included in every ORM record query."""
    from sqlalchemy import inspect
    from sqlalchemy.orm import column_property
    from sqlmodel import select

    from .record import Record
    from .server import Server, ServerLiveStatus

    mapper = inspect(Record)
    mapper.add_property(
        "native_server_name",
        column_property(
            select(ServerLiveStatus.hostname)
            .where(ServerLiveStatus.server_id == Record.native_server_id)
            .scalar_subquery()
        ),
    )
    mapper.add_property(
        "native_group_id",
        column_property(
            select(Server.group_id)
            .where(Server.id == Record.native_server_id)
            .scalar_subquery()
        ),
    )
    mapper.add_property(
        "replay_available",
        column_property(
            select(RecordReplay.record_uuid)
            .where(
                RecordReplay.record_uuid == Record.uuid,
                col(RecordReplay.available).is_(True),
            )
            .exists()
        ),
    )


install_record_read_properties()
