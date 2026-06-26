from datetime import datetime

from sqlmodel import Field, SQLModel


class QQBindingCodePublic(SQLModel):
    code: str = Field(min_length=1)
    expires_at: datetime


class QQBindingTokenPayload(SQLModel):
    steamid64: str = Field(min_length=1, max_length=32)
    exp: int = Field(ge=0)
