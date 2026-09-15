import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index
from sqlmodel import Field, SQLModel

from .utils import generate_uuid7, get_datetime_utc


class PlayerHiddenMap(SQLModel, table=True):
    __tablename__ = "player_hidden_map"
    __table_args__ = (
        Index(
            "ux_player_hidden_map_player_map",
            "player_steamid64",
            "map_id",
            unique=True,
        ),
    )

    id: uuid.UUID = Field(default_factory=generate_uuid7, primary_key=True)
    player_steamid64: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("player.steamid64", ondelete="CASCADE"),
            nullable=False,
        )
    )
    map_id: int = Field(
        sa_column=Column(
            ForeignKey("map.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class PlayerHiddenMapCreate(SQLModel):
    map_id: int


class PlayerHiddenMapPublic(SQLModel):
    id: uuid.UUID
    map_id: int
    created_at: datetime
    updated_at: datetime


class PlayerHiddenMapsPublic(SQLModel):
    data: list[PlayerHiddenMapPublic]
    count: int
