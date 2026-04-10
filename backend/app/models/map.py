from datetime import datetime

from pydantic import computed_field
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    Index,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from .map_review_summary import MapReviewSummaryPublic
from .utils import LegacyDatetimeNamesMixin, get_datetime_utc


class MapBase(LegacyDatetimeNamesMixin):
    name: str = Field(max_length=255)
    filesize: int = Field(default=0, ge=0)
    validated: bool = Field(default=False)
    difficulty: int = Field(default=0, ge=0, le=8)
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        validation_alias="created_on",
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        validation_alias="updated_on",
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    approved_by_steamid64: int = Field(default=0, sa_type=BigInteger)
    workshop_id: int | None = Field(default=None, sa_type=BigInteger)
    authors: list[str] | None = Field(
        default=None, sa_column=Column(JSONB, nullable=True)
    )
    no_steamid_names: list[str] | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True),
    )
    synced_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )


class Map(MapBase, table=True):
    __table_args__ = (
        CheckConstraint(
            "difficulty >= 0 AND difficulty <= 8", name="ck_map_difficulty_range"
        ),
        Index("ix_map_name", "name"),
        Index("ix_map_validated", "validated"),
        Index("ix_map_difficulty", "difficulty"),
        Index("ix_map_created_at", "created_at"),
        Index("ix_map_updated_at", "updated_at"),
    )

    id: int = Field(primary_key=True)


class MapCompatPublicV0(SQLModel):
    id: int
    name: str
    filesize: int
    validated: bool
    difficulty: int
    created_on: datetime
    updated_on: datetime
    approved_by_steamid64: str
    workshop_id: int | None = Field(default=None, exclude=True)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def workshop_url(self) -> str | None:
        if self.workshop_id:
            return f"https://steamcommunity.com/sharedfiles/filedetails/?id={self.workshop_id}"
        return None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def download_url(self) -> str:
        return ""


class MapTiers(SQLModel):
    OVR: int
    KZT: int
    SKZ: int
    VNL: int


class MapRefPublic(SQLModel):
    id: int
    name: str


class MapPublic(SQLModel):
    id: int
    name: str
    filesize: int
    validated: bool
    tiers: MapTiers
    created_on: datetime
    updated_on: datetime
    approved_by_steamid64: str
    workshop_id: int | None = None
    synced_at: datetime
    authors: list[str] = Field(default_factory=list)
    no_steamid_names: list[str] = Field(default_factory=list)
    review_summary: MapReviewSummaryPublic | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def workshop_url(self) -> str | None:
        if self.workshop_id:
            return f"https://steamcommunity.com/sharedfiles/filedetails/?id={self.workshop_id}"
        return None


class MapSyncResult(SQLModel):
    processed: int
    created: int
    updated: int
    errors: int
