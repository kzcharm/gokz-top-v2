import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import field_validator, model_validator
from sqlalchemy import JSON, BigInteger, Column, DateTime, ForeignKey, Index, Integer
from sqlalchemy import Enum as SqlEnum
from sqlmodel import Field, SQLModel

from .utils import generate_uuid7, get_datetime_utc


class PollStatus(StrEnum):
    ACTIVE = "active"
    CLOSED = "closed"


def _enum_values(enum_class: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_class]


class PollOptionInput(SQLModel):
    label: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)

    @field_validator("label", mode="after")
    @classmethod
    def normalize_label(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("option label must not be blank")
        return value

    @field_validator("description", mode="after")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        return value.strip() if value and value.strip() else None


class PollCreate(SQLModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    ends_at: datetime | None = None
    max_selections: int = Field(default=1, ge=0, le=100)
    allow_vote_change: bool = True
    options: list[PollOptionInput] = Field(min_length=2, max_length=100)

    @field_validator("ends_at", mode="after")
    @classmethod
    def normalize_ends_at(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)

    @field_validator("title", mode="after")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("title must not be blank")
        return value

    @field_validator("description", mode="after")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        return value.strip() if value and value.strip() else None

    @model_validator(mode="after")
    def validate_limit(self) -> PollCreate:
        if self.max_selections != 0 and self.max_selections > len(self.options):
            raise ValueError("max_selections cannot exceed the number of options")
        return self


class PollUpdate(SQLModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    ends_at: datetime | None = None
    max_selections: int | None = Field(default=None, ge=0, le=100)
    allow_vote_change: bool | None = None
    status: PollStatus | None = None
    options: list[PollOptionInput] | None = Field(
        default=None, min_length=2, max_length=100
    )

    @field_validator("ends_at", mode="after")
    @classmethod
    def normalize_ends_at(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)

    @field_validator("title", mode="after")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        return value.strip() if value else value

    @field_validator("description", mode="after")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        return value.strip() if value and value.strip() else None


class PollListQuery(SQLModel):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)
    status: PollStatus | None = None
    sort: Literal["created", "activity", "votes"] = "created"


class PollVoteCreate(SQLModel):
    option_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)


class PollOption(SQLModel, table=True):
    __tablename__ = "poll_option"
    __table_args__ = (Index("ix_poll_option_poll_position", "poll_id", "position"),)

    id: uuid.UUID = Field(default_factory=generate_uuid7, primary_key=True)
    poll_id: uuid.UUID = Field(foreign_key="poll.id", ondelete="CASCADE")
    label: str = Field(max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    position: int = Field(sa_type=Integer)


class Poll(SQLModel, table=True):
    __tablename__ = "poll"
    __table_args__ = (
        Index("ix_poll_status_created_at", "status", "created_at"),
        Index("ix_poll_last_activity_at", "last_activity_at"),
    )

    id: uuid.UUID = Field(default_factory=generate_uuid7, primary_key=True)
    created_by_steamid64: int | None = Field(
        default=None,
        sa_column=Column(
            BigInteger,
            ForeignKey("user.steamid64", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    deleted_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    title: str = Field(max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    status: PollStatus = Field(
        default=PollStatus.ACTIVE,
        sa_column=Column(
            SqlEnum(PollStatus, name="poll_status", values_callable=_enum_values),
            nullable=False,
        ),
    )
    ends_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    closed_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    max_selections: int = Field(
        default=1, ge=0, sa_column=Column(Integer, nullable=False)
    )
    allow_vote_change: bool = True
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    last_activity_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class PollVote(SQLModel, table=True):
    __tablename__ = "poll_vote"
    __table_args__ = (
        Index("ux_poll_vote_poll_user", "poll_id", "user_steamid64", unique=True),
    )

    id: uuid.UUID = Field(default_factory=generate_uuid7, primary_key=True)
    poll_id: uuid.UUID = Field(foreign_key="poll.id", ondelete="CASCADE")
    user_steamid64: int = Field(
        sa_column=Column(
            BigInteger, ForeignKey("user.steamid64", ondelete="CASCADE"), nullable=False
        )
    )
    option_ids: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class PollOptionPublic(SQLModel):
    id: uuid.UUID
    label: str
    description: str | None
    position: int
    votes: int | None = None
    percentage: float | None = None


class PollPublic(SQLModel):
    id: uuid.UUID
    created_by_steamid64: str | None
    title: str
    description: str | None
    status: PollStatus
    ends_at: datetime | None
    closed_at: datetime | None
    max_selections: int
    allow_vote_change: bool
    created_at: datetime
    updated_at: datetime
    last_activity_at: datetime
    total_votes: int
    has_voted: bool
    selected_option_ids: list[uuid.UUID]
    can_view_results: bool
    options: list[PollOptionPublic]


class PollsPublic(SQLModel):
    data: list[PollPublic]
    count: int


class PollVoterPublic(SQLModel):
    steamid64: str
    option_ids: list[uuid.UUID]
    voted_at: datetime


class AdminPollPublic(PollPublic):
    voters: list[PollVoterPublic]


class AdminPollsPublic(SQLModel):
    data: list[AdminPollPublic]
    count: int
