from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String
from sqlmodel import Field, SQLModel

from .utils import get_datetime_utc


class RecordFilterBase(SQLModel):
    map_id: int = Field(sa_type=Integer)
    stage: int = Field(default=0, ge=0, sa_type=Integer)
    mode_id: int = Field(foreign_key="mode.id", sa_type=Integer)
    tickrate: int = Field(ge=1, sa_type=Integer)
    has_teleports: bool = Field(default=False, sa_type=Boolean)
    tier: int | None = Field(default=None, ge=0, le=8, sa_type=Integer)
    created_on: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore[arg-type]
    )
    updated_on: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore[arg-type]
    )
    updated_by_id: str | None = Field(
        default=None,
        max_length=32,
        sa_type=String(32),
    )


class RecordFilter(RecordFilterBase, table=True):
    __tablename__ = "record_filter"
    __table_args__ = (
        Index(
            "ix_record_filter_lookup",
            "map_id",
            "stage",
            "mode_id",
            "tickrate",
            "has_teleports",
            "id",
        ),
        Index(
            "ix_record_filter_availability",
            "stage",
            "mode_id",
            "map_id",
            "has_teleports",
            "id",
        ),
    )

    id: int = Field(primary_key=True, sa_type=Integer)


class RecordFilterCompatPublicV0(SQLModel):
    id: int
    map_id: int
    stage: int
    mode_id: int
    tickrate: int
    has_teleports: bool
    created_on: datetime
    updated_on: datetime
    updated_by_id: str | None = None
