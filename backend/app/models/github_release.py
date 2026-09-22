from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, Text
from sqlmodel import Field, SQLModel

from .content_reaction import ReactionSummaryPublic
from .utils import get_datetime_utc


class GitHubRelease(SQLModel, table=True):
    __tablename__ = "github_release"

    id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    tag_name: str = Field(max_length=255)
    name: str | None = Field(default=None, max_length=255)
    html_url: str = Field(max_length=1000)
    published_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    body: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    is_listed: bool = Field(default=True, nullable=False)
    synced_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class GitHubReleasePublic(SQLModel):
    id: int
    tag_name: str
    name: str | None
    html_url: str
    published_at: datetime | None
    body: str | None
    reactions: ReactionSummaryPublic = Field(default_factory=ReactionSummaryPublic)


class GitHubReleasesPublic(SQLModel):
    data: list[GitHubReleasePublic]
