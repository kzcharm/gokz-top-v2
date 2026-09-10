from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, Text
from sqlmodel import Field, SQLModel

from .utils import get_datetime_utc


class WorkshopPreviewUrlCache(SQLModel, table=True):
    __tablename__ = "workshop_preview_urls"
    __table_args__ = {"schema": "cache"}

    workshop_id: int = Field(
        sa_column=Column(BigInteger, primary_key=True, nullable=False)
    )
    preview_url: str | None = Field(default=None, max_length=1000)
    fetched_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    last_attempted_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    error_message: str | None = Field(default=None, sa_column=Column(Text))
