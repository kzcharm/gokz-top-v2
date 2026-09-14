from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Column, DateTime, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from .utils import get_datetime_utc


class AppSettingKey(StrEnum):
    COMMUNITY_LINKS = "community_links"
    QQ_BINDING_SECRET = "qq_binding_secret"


class CommunityLinksLocation(StrEnum):
    NAVBAR = "navbar"
    FOOTER = "footer"


class CommunityLinksSettingValue(SQLModel):
    location: CommunityLinksLocation = CommunityLinksLocation.NAVBAR


class QQBindingSecretSettingValue(SQLModel):
    encrypted_secret: str = Field(min_length=1)


class AppSetting(SQLModel, table=True):
    __tablename__ = "app_setting"

    key: str = Field(sa_column=Column(Text, primary_key=True, nullable=False))
    value: dict[str, Any] = Field(sa_column=Column(JSONB, nullable=False))
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class AppSettingsPublic(SQLModel):
    community_links_location: CommunityLinksLocation


class AppSettingsUpdate(SQLModel):
    community_links_location: CommunityLinksLocation
