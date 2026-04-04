from datetime import date, datetime

from sqlalchemy import BigInteger, Column, Date, DateTime, ForeignKey, Index
from sqlmodel import Field, SQLModel

from .utils import get_datetime_utc


class PlayerProfileView(SQLModel, table=True):
    __tablename__ = "player_profile_view"
    __table_args__ = (
        Index(
            "ix_player_profile_view_target_view_date",
            "target_steamid64",
            "view_date",
        ),
    )

    viewer_steamid64: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("user.steamid64", ondelete="CASCADE"),
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
    view_date: date = Field(primary_key=True, sa_type=Date)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
