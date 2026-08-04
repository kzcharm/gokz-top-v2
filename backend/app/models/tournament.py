import uuid
from datetime import date, datetime
from enum import StrEnum
from urllib.parse import urlparse

from pydantic import field_validator, model_validator
from sqlalchemy import BigInteger, CheckConstraint, Column, DateTime, ForeignKey, Index
from sqlalchemy import Enum as SqlEnum
from sqlmodel import Field, SQLModel

from .player import PlayerRefPublic
from .utils import generate_uuid7, get_datetime_utc


def _enum_values(enum_class: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_class]


class TournamentLevel(StrEnum):
    S = "S"
    A = "A"
    B = "B"
    C = "C"


def normalize_tournament_url(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("official_url must be a valid HTTP(S) URL")
    return normalized


class TournamentBase(SQLModel):
    name: str = Field(min_length=1, max_length=255)
    starts_on: date
    ends_on: date
    official_url: str | None = Field(default=None, max_length=500)
    level: TournamentLevel = Field(
        sa_column=Column(
            SqlEnum(
                TournamentLevel,
                name="tournament_level",
                values_callable=_enum_values,
            ),
            nullable=False,
        )
    )

    @field_validator("name", mode="after")
    @classmethod
    def _normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("name must not be blank")
        return normalized

    @field_validator("official_url", mode="after")
    @classmethod
    def _normalize_official_url(cls, value: str | None) -> str | None:
        return normalize_tournament_url(value)

    @model_validator(mode="after")
    def _validate_date_range(self) -> TournamentBase:
        if self.ends_on is not None and self.ends_on < self.starts_on:
            raise ValueError("ends_on must not be before starts_on")
        return self


class Tournament(TournamentBase, table=True):
    __tablename__ = "tournament"
    __table_args__ = (
        CheckConstraint("ends_on >= starts_on", name="ck_tournament_date_range"),
        Index("ix_tournament_ends_on", "ends_on"),
    )

    id: uuid.UUID = Field(default_factory=generate_uuid7, primary_key=True)
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )


class TournamentAchievement(SQLModel, table=True):
    __tablename__ = "tournament_achievement"
    __table_args__ = (
        CheckConstraint(
            "placement BETWEEN 1 AND 4", name="ck_tournament_achievement_placement"
        ),
        Index(
            "ux_tournament_achievement_tournament_player",
            "tournament_id",
            "player_steamid64",
            unique=True,
        ),
        Index("ix_tournament_achievement_player_steamid64", "player_steamid64"),
    )

    id: uuid.UUID = Field(default_factory=generate_uuid7, primary_key=True)
    tournament_id: uuid.UUID = Field(
        sa_column=Column(
            ForeignKey("tournament.id", ondelete="CASCADE"), nullable=False
        )
    )
    player_steamid64: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("player.steamid64", ondelete="CASCADE"),
            nullable=False,
        )
    )
    placement: int = Field(ge=1, le=4)
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )


class TournamentCreate(TournamentBase):
    ends_on: date | None = None

    @model_validator(mode="after")
    def _default_end_date(self) -> TournamentCreate:
        if self.ends_on is None:
            self.ends_on = self.starts_on
        return self


class TournamentUpdate(SQLModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    starts_on: date | None = None
    ends_on: date | None = None
    official_url: str | None = Field(default=None, max_length=500)
    level: TournamentLevel | None = None

    @field_validator("name", mode="after")
    @classmethod
    def _normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("name must not be blank")
        return normalized

    @field_validator("official_url", mode="after")
    @classmethod
    def _normalize_official_url(cls, value: str | None) -> str | None:
        return normalize_tournament_url(value)


class TournamentPublic(TournamentBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class TournamentsPublic(SQLModel):
    data: list[TournamentPublic]
    count: int


class TournamentListQuery(SQLModel):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)


class TournamentAchievementCreate(SQLModel):
    tournament_id: uuid.UUID
    player_steamid64: str = Field(min_length=1, max_length=32)
    placement: int = Field(ge=1, le=4)


class TournamentAchievementUpdate(SQLModel):
    placement: int = Field(ge=1, le=4)


class TournamentAchievementPublic(SQLModel):
    id: uuid.UUID
    tournament: TournamentPublic
    placement: int = Field(ge=1, le=4)
    created_at: datetime
    updated_at: datetime


class TournamentAchievementsPublic(SQLModel):
    data: list[TournamentAchievementPublic]
    count: int


class AdminTournamentAchievementPublic(TournamentAchievementPublic):
    player: PlayerRefPublic


class AdminTournamentAchievementsPublic(SQLModel):
    data: list[AdminTournamentAchievementPublic]
    count: int
