from datetime import datetime
from enum import StrEnum

from pydantic import ConfigDict, field_validator
from sqlalchemy import BigInteger, Column, DateTime, ForeignKey
from sqlalchemy import Enum as SqlEnum
from sqlmodel import Field, SQLModel

from .player import (
    MAX_PLAYER_CUSTOM_ID_LENGTH,
    PlayerPublic,
    normalize_player_country,
    validate_player_custom_id,
    validate_player_settings_alias,
)
from .utils import get_datetime_utc


def _enum_values(enum_class: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_class]


class PlayerAction(StrEnum):
    ALIAS_CHANGE = "alias_change"
    CUSTOM_ID_CHANGE = "custom_id_change"
    COUNTRY_MANUAL_OVERRIDE = "country_manual_override"
    FRIENDS_SYNC = "friends_sync"


class PlayerProfileField(StrEnum):
    ALIAS = "alias"
    CUSTOM_ID = "custom_id"
    COUNTRY = "country"


PLAYER_PROFILE_FIELD_ACTION_MAP = {
    PlayerProfileField.ALIAS: PlayerAction.ALIAS_CHANGE,
    PlayerProfileField.CUSTOM_ID: PlayerAction.CUSTOM_ID_CHANGE,
    PlayerProfileField.COUNTRY: PlayerAction.COUNTRY_MANUAL_OVERRIDE,
}


class PlayerActionTimestamp(SQLModel, table=True):
    __tablename__ = "player_action_timestamp"

    player_steamid64: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("player.steamid64", ondelete="CASCADE"),
            primary_key=True,
        )
    )
    action: PlayerAction = Field(
        sa_column=Column(
            SqlEnum(
                PlayerAction,
                name="player_action",
                values_callable=_enum_values,
            ),
            primary_key=True,
        )
    )
    recorded_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )


class PlayerProfileFieldStatus(SQLModel):
    last_changed_at: datetime | None = None
    next_available_at: datetime | None = None
    can_change: bool = True


class PlayerSettingsPublic(SQLModel):
    player: PlayerPublic
    alias: PlayerProfileFieldStatus
    custom_id: PlayerProfileFieldStatus
    country: PlayerProfileFieldStatus
    country_locked: bool = False


class PlayerSettingsUpdate(SQLModel):
    model_config = ConfigDict(extra="forbid")

    alias: str | None = Field(default=None, max_length=25)
    custom_id: str | None = Field(default=None, max_length=MAX_PLAYER_CUSTOM_ID_LENGTH)
    country: str | None = Field(default=None, max_length=2)

    @field_validator("alias", mode="after")
    @classmethod
    def normalize_alias(cls, value: str | None) -> str | None:
        return validate_player_settings_alias(value)

    @field_validator("custom_id", mode="after")
    @classmethod
    def normalize_custom_id(cls, value: str | None) -> str | None:
        return validate_player_custom_id(value)

    @field_validator("country", mode="after")
    @classmethod
    def normalize_country(cls, value: str | None) -> str | None:
        return normalize_player_country(value)
