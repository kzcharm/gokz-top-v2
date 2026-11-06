"""Browser-only records; deliberately independent of native records and rankings."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict
from pydantic import Field as PydanticField
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    Index,
    UniqueConstraint,
)
from sqlmodel import Field, SQLModel

from .utils import get_datetime_utc

WebMode = Literal["KZT", "SKZ", "VNL", "NKZ"]
MapName = Annotated[str, PydanticField(pattern=r"^[a-zA-Z0-9_-]{1,128}$")]


class WebPlayer(SQLModel, table=True):
    __tablename__ = "players"
    __table_args__ = {"schema": "web_gokz"}
    steamid64: int = Field(primary_key=True, sa_type=BigInteger)


class WebMap(SQLModel, table=True):
    __tablename__ = "maps"
    __table_args__ = (UniqueConstraint("name", "version"), {"schema": "web_gokz"})
    id: uuid.UUID = Field(default_factory=uuid.uuid7, primary_key=True)
    name: str = Field(max_length=128)
    version: str = Field(max_length=128)


class WebCourse(SQLModel, table=True):
    __tablename__ = "map_courses"
    __table_args__ = (UniqueConstraint("map_id", "course"), {"schema": "web_gokz"})
    id: uuid.UUID = Field(default_factory=uuid.uuid7, primary_key=True)
    map_id: uuid.UUID = Field(foreign_key="web_gokz.maps.id")
    course: int


class WebTime(SQLModel, table=True):
    __tablename__ = "times"
    __table_args__ = (
        UniqueConstraint("player_steamid64", "submission_id"),
        CheckConstraint("time_ms > 0 AND teleports >= 0"),
        Index(
            "ix_web_times_top", "course_id", "mode", "engine_version", "time_ms", "id"
        ),
        {"schema": "web_gokz"},
    )
    id: uuid.UUID = Field(default_factory=uuid.uuid7, primary_key=True)
    submission_id: uuid.UUID
    player_steamid64: int = Field(
        foreign_key="web_gokz.players.steamid64", sa_type=BigInteger
    )
    course_id: uuid.UUID = Field(foreign_key="web_gokz.map_courses.id")
    mode: str = Field(max_length=3)
    engine_version: str = Field(max_length=128)
    time_ms: int
    teleports: int
    room_id: int | None = None
    room_generation: uuid.UUID | None = None
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class WebIdentity(BaseModel):
    steamid64: str
    name: str
    avatarfull: str | None = None
    avatar_hash: str | None = None


class WebSession(BaseModel):
    access_token: str
    player: WebIdentity


class WebLaunch(BaseModel):
    code: str
    expires_in: int = 60


class WebExchange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = PydanticField(pattern=r"^[A-Za-z0-9_-]{43}$")


class WebFinish(BaseModel):
    model_config = ConfigDict(extra="forbid")
    submission_id: uuid.UUID
    map_name: MapName
    map_version: str = PydanticField(min_length=1, max_length=128)
    engine_version: str = PydanticField(min_length=1, max_length=128)
    mode: WebMode
    course: int = PydanticField(default=0, ge=0, le=1000)
    time_ms: int = PydanticField(gt=0, le=604800000, strict=True)
    teleports: int = PydanticField(ge=0, le=1000000, strict=True)
    room_id: Literal[1, 2] | None = None
    room_generation: uuid.UUID | None = None


class WebRecord(BaseModel):
    id: uuid.UUID
    player: WebIdentity
    map_name: str
    map_version: str
    engine_version: str
    mode: str
    course: int
    time_ms: int
    teleports: int
    created_at: datetime
    source: Literal["solo", "room"]
    verification: Literal["client-submitted"] = "client-submitted"


class WebRecords(BaseModel):
    data: list[WebRecord]
    count: int
