from datetime import datetime

from pydantic import model_validator
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy import Enum as SqlEnum
from sqlmodel import Field, SQLModel

from .record import KZMode, kz_mode_to_legacy_mode_id, normalize_kz_mode
from .utils import LegacyDatetimeNamesMixin, get_datetime_utc


def _normalize_record_filter_payload(data: dict[str, object]) -> dict[str, object]:
    payload = dict(data)
    if "mode" not in payload and "mode_id" in payload:
        payload["mode"] = normalize_kz_mode(payload.pop("mode_id"))
    elif "mode" in payload:
        payload["mode"] = normalize_kz_mode(payload["mode"])
    return payload


class RecordFilterBase(LegacyDatetimeNamesMixin):
    map_id: int = Field(sa_type=Integer)
    stage: int = Field(default=0, ge=0, sa_type=Integer)
    mode: KZMode = Field(
        sa_column=Column(
            SqlEnum(KZMode, name="kz_mode"),
            ForeignKey("mode.name_short"),
            nullable=False,
        )
    )
    tickrate: int = Field(ge=1, sa_type=Integer)
    has_teleports: bool = Field(default=False, sa_type=Boolean)
    tier: int | None = Field(default=None, ge=0, le=8, sa_type=Integer)
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
    updated_by_id: str | None = Field(
        default=None,
        max_length=32,
        sa_type=String(32),
    )

    def __init__(self, /, **data: object) -> None:
        super().__init__(**_normalize_record_filter_payload(data))

    @model_validator(mode="before")
    @classmethod
    def _normalize_mode_id_input(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        return _normalize_record_filter_payload(data)

    @property
    def mode_id(self) -> int:
        return kz_mode_to_legacy_mode_id(self.mode)


class RecordFilter(RecordFilterBase, table=True):
    __tablename__ = "record_filter"
    __table_args__ = (
        Index(
            "ix_record_filter_lookup",
            "map_id",
            "stage",
            "mode",
            "tickrate",
            "has_teleports",
            "id",
        ),
        Index(
            "ix_record_filter_availability",
            "stage",
            "mode",
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


class AdminRecordFilterPublic(SQLModel):
    id: int
    map_id: int
    stage: int
    mode: KZMode
    has_teleports: bool
    tier: int | None
    created_on: datetime
    updated_on: datetime
    updated_by_id: str | None = None


class AdminRecordFilterStagePublic(SQLModel):
    stage: int
    record_filters: list[AdminRecordFilterPublic]


class AdminMapRecordFiltersPublic(SQLModel):
    map_id: int
    stages: list[AdminRecordFilterStagePublic]


class AdminRecordFilterTierUpdate(SQLModel):
    model_config = {"extra": "forbid"}

    tier: int | None = Field(ge=0, le=8)
