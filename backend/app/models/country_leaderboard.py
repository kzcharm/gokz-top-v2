from pydantic import field_serializer
from sqlmodel import Field, SQLModel

from .leaderboard_player import scale_public_rating
from .mode_scope import ModeScope
from .player import PlayerRefPublic


class CountryLeaderboardEntryPublic(SQLModel):
    rank: int | None
    country: str | None
    ranked_players: int = Field(ge=0)
    active_players: int = Field(ge=0)
    top_players: list[PlayerRefPublic]
    median_rating: float | None
    top10_average_rating: float | None

    @field_serializer("median_rating", "top10_average_rating")
    def serialize_rating(self, value: float | None) -> float | None:
        return scale_public_rating(value)


class CountryLeaderboardsPublic(SQLModel):
    data: list[CountryLeaderboardEntryPublic]
    count: int


class CountryLeaderboardListQuery(SQLModel):
    scope: ModeScope = ModeScope.OVR
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=200)
