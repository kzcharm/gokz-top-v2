from sqlalchemy import BigInteger, CheckConstraint, Index
from sqlmodel import Field

from .pronunciation import PronunciationFields, PronunciationPublic


class PlayerPronunciation(PronunciationFields, table=True):
    __tablename__ = "player_pronunciation"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'generating', 'ready', 'failed')",
            name="ck_player_pronunciation_status",
        ),
        Index("ix_player_pronunciation_queue", "status", "next_attempt_at"),
    )
    steamid64: int = Field(
        primary_key=True,
        foreign_key="player.steamid64",
        ondelete="CASCADE",
        sa_type=BigInteger,
    )


class PlayerPronunciationPublic(PronunciationPublic):
    pass
