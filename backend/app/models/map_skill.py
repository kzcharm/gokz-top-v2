from decimal import Decimal

from sqlalchemy import CheckConstraint, Column, ForeignKey, Integer, Numeric
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class MapSkill(SQLModel, table=True):
    __tablename__ = "map_skill"
    __table_args__ = tuple(
        CheckConstraint(f"{skill} BETWEEN 0 AND 1", name=f"ck_map_skill_{skill}_range")
        for skill in ("boxtech", "strafe", "bhop", "climb", "ladder", "slide")
    )

    map_id: int = Field(
        sa_column=Column(
            Integer, ForeignKey("map.id", ondelete="CASCADE"), primary_key=True
        )
    )
    boxtech: Decimal = Field(sa_column=Column(Numeric(5, 4), nullable=False))
    strafe: Decimal = Field(sa_column=Column(Numeric(5, 4), nullable=False))
    bhop: Decimal = Field(sa_column=Column(Numeric(5, 4), nullable=False))
    climb: Decimal = Field(sa_column=Column(Numeric(5, 4), nullable=False))
    ladder: Decimal = Field(sa_column=Column(Numeric(5, 4), nullable=False))
    slide: Decimal = Field(sa_column=Column(Numeric(5, 4), nullable=False))
    segments: list[dict[str, str | int]] = Field(
        sa_column=Column(JSONB, nullable=False)
    )


class MapSkillsPublic(SQLModel):
    boxtech: float
    strafe: float
    bhop: float
    climb: float
    ladder: float
    slide: float
