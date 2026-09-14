from datetime import datetime

from sqlmodel import Field, SQLModel


class QQBindingSecretStored(SQLModel):
    encrypted_secret: str = Field(min_length=1)
    created_at: datetime
    updated_at: datetime


class QQBindingSecretStatusPublic(SQLModel):
    configured: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


class QQBindingSecretPublic(SQLModel):
    secret: str = Field(min_length=1)
