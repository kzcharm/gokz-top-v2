from datetime import datetime

from sqlalchemy import DateTime, Text
from sqlmodel import Column, Field, SQLModel

from .utils import get_datetime_utc


class QQBindingSecret(SQLModel, table=True):
    __tablename__ = "qq_binding_secret"

    id: int = Field(default=1, primary_key=True)
    encrypted_secret: str = Field(sa_column=Column(Text, nullable=False))
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore[arg-type]
    )
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore[arg-type]
    )


class QQBindingSecretStatusPublic(SQLModel):
    configured: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


class QQBindingSecretPublic(SQLModel):
    secret: str = Field(min_length=1)
