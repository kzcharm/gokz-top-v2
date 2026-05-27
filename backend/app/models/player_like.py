from datetime import date, datetime

from sqlalchemy import BigInteger, Column, Date, DateTime, ForeignKey, Index
from sqlmodel import Field, SQLModel

from .utils import get_datetime_utc


class PlayerLike(SQLModel, table=True):
    __tablename__ = "player_like"
    __table_args__ = (
        Index(
            "ix_player_like_target_like_date",
            "target_steamid64",
            "like_date",
        ),
    )

    viewer_steamid64: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("player.steamid64", ondelete="CASCADE"),
            primary_key=True,
        )
    )
    target_steamid64: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("player.steamid64", ondelete="CASCADE"),
            primary_key=True,
        )
    )
    like_date: date = Field(primary_key=True, sa_type=Date)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
