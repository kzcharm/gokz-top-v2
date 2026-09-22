from typing import Any

from sqlalchemy import Column, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class LJRoomSpot(SQLModel):
    model_config = {"extra": "forbid"}

    distance: int = Field(gt=0)
    raw_distance: float = Field(gt=0)
    origin: tuple[float, float, float]
    angles: tuple[float, float]
    landing: tuple[float, float, float]


class LJRoom(SQLModel):
    model_config = {"extra": "forbid"}

    rank: int = Field(ge=0)
    score: float = Field(ge=0)
    spots: list[LJRoomSpot]


class MapLJRoomPayload(SQLModel):
    model_config = {"extra": "forbid"}

    map_name: str = Field(min_length=1, max_length=255)
    api_map_id: int = Field(gt=0)
    filesize: int = Field(ge=0)
    rooms: list[LJRoom]


class MapLJRoom(SQLModel, table=True):
    __tablename__ = "map_lj_room"

    id: int = Field(
        sa_column=Column(
            Integer, ForeignKey("map.id", ondelete="CASCADE"), primary_key=True
        )
    )
    data: dict[str, Any] = Field(sa_column=Column(JSONB, nullable=False))
