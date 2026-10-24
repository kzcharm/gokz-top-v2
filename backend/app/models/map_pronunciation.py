from sqlalchemy import CheckConstraint, Index
from sqlmodel import Field

from .pronunciation import (  # noqa: F401
    PronunciationFields,
    PronunciationPublic,
    PronunciationStatus,
)


class MapPronunciation(PronunciationFields, table=True):
    __tablename__ = "map_pronunciation"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'generating', 'ready', 'failed')",
            name="ck_map_pronunciation_status",
        ),
        Index("ix_map_pronunciation_queue", "status", "next_attempt_at"),
    )
    map_id: int = Field(primary_key=True, foreign_key="map.id", ondelete="CASCADE")


class MapPronunciationPublic(PronunciationPublic):
    pass
