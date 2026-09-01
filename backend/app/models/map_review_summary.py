from datetime import datetime

from sqlalchemy import Column, DateTime
from sqlmodel import Field, SQLModel

from .utils import get_datetime_utc


class MapReviewSummaryCache(SQLModel, table=True):
    __tablename__ = "map_review_summaries"
    __table_args__ = {"schema": "cache"}

    map_id: int = Field(
        foreign_key="map.id",
        primary_key=True,
        ondelete="CASCADE",
    )
    overall_avg: float
    gameplay_avg: float | None = None
    visuals_avg: float | None = None
    reviews_count: int
    gameplay_count: int
    visuals_count: int
    comments_count: int
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class MapReviewSummaryPublic(SQLModel):
    overall_avg: float
    overall_adjusted: float
    gameplay_avg: float | None = None
    visuals_avg: float | None = None
    reviews_count: int
    gameplay_count: int
    visuals_count: int
    comments_count: int
    updated_at: datetime
