from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import BigInteger, DateTime
from sqlmodel import Field, SQLModel

from .utils import get_datetime_utc


@dataclass(frozen=True)
class CanonicalModeSeed:
    id: int
    name: str
    name_short: str
    id_plugin: int
    description: str
    latest_version: int
    latest_version_description: str
    website: str
    repo: str
    contact_steamid64: int
    updated_by_id: int


CANONICAL_MODE_SEEDS: tuple[CanonicalModeSeed, ...] = (
    CanonicalModeSeed(
        id=200,
        name="kz_timer",
        name_short="KZT",
        id_plugin=2,
        description="KZTimerGlobal mode.  Bunch of jumps and bhops and stuff.",
        latest_version=2171,
        latest_version_description="1.106",
        website="forum.gokz.org",
        repo="https://bitbucket.org/kztimerglobalteam/kztimerglobal",
        contact_steamid64=76561198165203332,
        updated_by_id=76561198003275951,
    ),
    CanonicalModeSeed(
        id=201,
        name="kz_simple",
        name_short="SKZ",
        id_plugin=1,
        description="SimpleKZ mode. RNG? We don't need no stinkin RNG.",
        latest_version=211,
        latest_version_description="3.6.3",
        website="forum.gokz.org",
        repo="https://github.com/KZGlobalTeam/gokz",
        contact_steamid64=76561197989817982,
        updated_by_id=76561198003275951,
    ),
    CanonicalModeSeed(
        id=202,
        name="kz_vanilla",
        name_short="VNL",
        id_plugin=0,
        description="Vanilla mode. We need RNG.",
        latest_version=171,
        latest_version_description="3.6.3",
        website="forum.gokz.org",
        repo="https://github.com/KZGlobalTeam/gokz",
        contact_steamid64=76561197989817982,
        updated_by_id=76561197989817982,
    ),
    CanonicalModeSeed(
        id=203,
        name="kz_noperfkz",
        name_short="NKZ",
        id_plugin=3,
        description="NoPerfKZ mode. We don't need no stinkin RNG",
        latest_version=171,
        latest_version_description="3.6.3",
        website="gokz.top",
        repo="https://github.com/KZGlobalTeam/gokz",
        contact_steamid64=76561199022242130,
        updated_by_id=76561199022242130,
    ),
)


class ModeBase(SQLModel):
    name: str = Field(max_length=255, sa_column_kwargs={"unique": True})
    name_short: str = Field(max_length=16, sa_column_kwargs={"unique": True})
    id_plugin: int = Field(sa_column_kwargs={"unique": True})
    description: str = Field(max_length=1023)
    latest_version: int = Field(default=0, ge=0)
    latest_version_description: str = Field(max_length=255)
    website: str = Field(max_length=255)
    repo: str = Field(max_length=255)
    contact_steamid64: int = Field(sa_type=BigInteger)
    created_on: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    updated_on: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    updated_by_id: int = Field(sa_type=BigInteger)


class Mode(ModeBase, table=True):
    id: int = Field(primary_key=True)


class ModePublic(SQLModel):
    id: int
    name: str
    name_short: str
    id_plugin: int
    description: str
    latest_version: int
    latest_version_description: str
    website: str
    repo: str
    contact_steamid64: str
    supported_tickrates: list[int] | None = None
    created_on: datetime | None = None
    updated_on: datetime | None = None
    updated_by_id: str


class ModeCompatPublicV0(SQLModel):
    id: int
    name: str
    description: str
    latest_version: int
    latest_version_description: str
    website: str
    repo: str
    contact_steamid64: int
    supported_tickrates: list[int] | None = None
    created_on: datetime | None = None
    updated_on: datetime | None = None
    updated_by_id: int


class ModeAdminUpdate(SQLModel):
    model_config = {"extra": "forbid"}

    description: str | None = Field(default=None, max_length=1023)
    latest_version: int | None = Field(default=None, ge=0)
    latest_version_description: str | None = Field(default=None, max_length=255)
    website: str | None = Field(default=None, max_length=255)
    repo: str | None = Field(default=None, max_length=255)
    contact_steamid64: str | None = Field(default=None, max_length=32)
