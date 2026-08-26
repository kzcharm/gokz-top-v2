from sqlmodel import Field, SQLModel

from .leaderboard_player import PlayerLeaderboardRankPublic
from .mode_scope import ModeScope
from .record import RecordPublic


class PlayerCompareTierPublic(SQLModel):
    tier: int = Field(ge=1, le=8)
    total_maps: int = Field(ge=0)
    player1_finished: int = Field(ge=0)
    player2_finished: int = Field(ge=0)


class PlayerCompareRunPublic(SQLModel):
    map_id: int
    map_name: str
    map_tier: int = Field(ge=0, le=8)
    player1: RecordPublic | None = None
    player2: RecordPublic | None = None
    time_delta: float | None = None
    points_delta: int | None = None


class PlayerComparisonPublic(SQLModel):
    scope: ModeScope
    player1: PlayerLeaderboardRankPublic
    player2: PlayerLeaderboardRankPublic
    progression: list[PlayerCompareTierPublic]
    nub_runs: list[PlayerCompareRunPublic]
    pro_runs: list[PlayerCompareRunPublic]
