from datetime import date, datetime

from sqlalchemy import BigInteger, Column, Date, DateTime, ForeignKey, Index, Text
from sqlmodel import Field, SQLModel

from .utils import get_datetime_utc


class MapFileDistribution(SQLModel, table=True):
    __tablename__ = "map_file_distribution"
    __table_args__ = (
        Index("ix_map_file_distribution_map_name", "map_name"),
        Index("ix_map_file_distribution_synced_at", "synced_at"),
    )

    map_id: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("map.id", ondelete="CASCADE"),
            primary_key=True,
        )
    )
    map_name: str = Field(max_length=255)
    workshop_id: int | None = Field(default=None, sa_type=BigInteger)
    map_updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    bsp_size: int | None = Field(default=None, sa_type=BigInteger)
    bsp_sha256: str | None = Field(default=None, max_length=64)
    bsp_r2_key: str | None = Field(default=None, max_length=1000)
    bsp_download_url: str | None = Field(default=None, max_length=1000)
    bz2_size: int | None = Field(default=None, sa_type=BigInteger)
    bz2_r2_key: str | None = Field(default=None, max_length=1000)
    bz2_download_url: str | None = Field(default=None, max_length=1000)
    source: str | None = Field(default=None, max_length=32)
    synced_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    uploaded_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    last_error: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )


class MapPackageRelease(SQLModel, table=True):
    __tablename__ = "map_package_release"

    release_date: date = Field(
        sa_column=Column(Date, primary_key=True),
    )
    package_key: str = Field(max_length=1000)
    package_url: str = Field(max_length=1000)
    file_size: int = Field(default=0, ge=0, sa_type=BigInteger)
    map_count: int = Field(default=0, ge=0)
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(
            DateTime(timezone=True), nullable=False, default=get_datetime_utc
        ),
    )
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(
            DateTime(timezone=True), nullable=False, default=get_datetime_utc
        ),
    )


class MapFileDistributionSyncResult(SQLModel):
    processed: int = 0
    downloaded: int = 0
    uploaded: int = 0
    bz2_uploaded: int = 0
    package_uploaded: int = 0
    release_packages_uploaded: int = 0
    skipped: int = 0
    errors: int = 0
    warnings: int = 0
    disabled: bool = False


class MapFileSeedResult(SQLModel):
    processed: int = 0
    extracted: int = 0
    package_copied: bool = False
