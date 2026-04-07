from enum import StrEnum

from pydantic import field_validator
from sqlmodel import Field, SQLModel


class RegionCode(StrEnum):
    AF = "AF"
    AS = "AS"
    CIS = "CIS"
    CN = "CN"
    EU = "EU"
    ME = "ME"
    NA = "NA"
    OC = "OC"
    SA = "SA"


def normalize_region_code(region: str | None) -> str | None:
    if region is None:
        return None

    normalized = region.strip().upper()
    return normalized or None


class RegionPublic(SQLModel):
    code: RegionCode
    name: str
    country_codes: list[str]


class RegionsPublic(SQLModel):
    data: list[RegionPublic]
    count: int


class GeographyFilterMixin(SQLModel):
    country: str | None = Field(default=None, max_length=2)
    region: str | None = Field(default=None, max_length=3)

    @field_validator("country", mode="after")
    @classmethod
    def _normalize_country(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        return normalized or None

    @field_validator("region", mode="after")
    @classmethod
    def _normalize_region(cls, value: str | None) -> str | None:
        return normalize_region_code(value)
