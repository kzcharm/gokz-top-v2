import unicodedata
import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, HttpUrl, field_validator, model_validator
from pydantic import Field as PydanticField
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from .utils import get_datetime_utc


class ProductCategory(StrEnum):
    MOUSE = "mouse"
    MOUSE_PAD = "mouse_pad"
    KEYBOARD = "keyboard"
    MONITOR = "monitor"
    HEADSET = "headset"
    CPU = "cpu"
    GPU = "gpu"
    MEMORY = "memory"
    MOTHERBOARD = "motherboard"
    STORAGE = "storage"
    POWER_SUPPLY = "power_supply"
    CASE = "case"
    COOLING = "cooling"


def normalize_product_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


class ProductCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: ProductCategory
    brand: str = PydanticField(min_length=1, max_length=100)
    model: str = PydanticField(min_length=1, max_length=200)

    product_url: HttpUrl | None = PydanticField(default=None, max_length=2048)

    @field_validator("brand", "model", mode="before")
    @classmethod
    def clean_text(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("Enter text for the brand and model")
        return " ".join(unicodedata.normalize("NFKC", value).split())


class Product(SQLModel, table=True):
    __tablename__ = "product"
    __table_args__ = (
        UniqueConstraint(
            "category",
            "normalized_brand",
            "normalized_model",
            name="uq_product_identity",
        ),
        {"schema": "products"},
    )
    id: uuid.UUID = Field(default_factory=uuid.uuid7, primary_key=True)
    category: ProductCategory = Field(
        sa_column=Column(String(32), nullable=False, index=True)
    )
    brand: str = Field(max_length=100)
    model: str = Field(max_length=200)
    normalized_brand: str = Field(max_length=100)
    normalized_model: str = Field(max_length=200)
    created_by: int | None = Field(default=None, sa_type=BigInteger, index=True)
    created_at: datetime = Field(
        default_factory=get_datetime_utc, sa_column=Column(DateTime(timezone=True))
    )
    verified_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True))
    )
    source_url: str | None = None
    merged_into_id: uuid.UUID | None = Field(
        default=None, foreign_key="products.product.id", index=True
    )


class ProductAlias(SQLModel, table=True):
    __tablename__ = "product_alias"
    __table_args__ = (
        UniqueConstraint("product_id", "normalized_name"),
        {"schema": "products"},
    )
    id: uuid.UUID = Field(default_factory=uuid.uuid7, primary_key=True)
    product_id: uuid.UUID = Field(foreign_key="products.product.id", index=True)
    normalized_name: str = Field(max_length=301, index=True)


class ProductAudit(SQLModel, table=True):
    __tablename__ = "product_audit"
    __table_args__ = {"schema": "products"}
    id: uuid.UUID = Field(default_factory=uuid.uuid7, primary_key=True)
    created_at: datetime = Field(
        default_factory=get_datetime_utc, sa_column=Column(DateTime(timezone=True))
    )
    action: str
    details: dict[str, object] = Field(sa_column=Column(JSONB, nullable=False))


class ProductPublic(ProductCreate):
    id: uuid.UUID
    community_added: bool


class ProductsPublic(BaseModel):
    data: list[ProductPublic]
    count: int


class HardwareInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: ProductCategory
    product_id: uuid.UUID | None = None
    storage_capacity_unit: Literal["GB", "TB"] = "GB"
    storage_capacity_gb: int | None = PydanticField(default=None, gt=0, le=1000000000)
    memory_capacity_gb: int | None = PydanticField(default=None, gt=0, le=1048576)
    memory_type: str | None = PydanticField(default=None, pattern=r"^DDR[1-6]$")
    memory_speed_mts: int | None = PydanticField(default=None, gt=0, le=1000000)
    monitor_refresh_hz: Decimal | None = PydanticField(
        default=None, gt=0, le=10000, decimal_places=3, allow_inf_nan=False
    )

    @model_validator(mode="after")
    def validate_configuration(self) -> Self:
        memory = any(
            v is not None
            for v in (self.memory_capacity_gb, self.memory_type, self.memory_speed_mts)
        )
        if memory and self.category != ProductCategory.MEMORY:
            raise ValueError("Memory configuration requires the memory category")
        if (
            self.monitor_refresh_hz is not None
            and self.category != ProductCategory.MONITOR
        ):
            raise ValueError("Refresh rate requires the monitor category")
        if (
            self.storage_capacity_gb is not None
            and self.category != ProductCategory.STORAGE
        ):
            raise ValueError("Storage capacity requires the storage category")
        if (
            self.product_id is None
            and not (
                self.category == ProductCategory.STORAGE
                and self.storage_capacity_gb is not None
            )
            and not (self.category == ProductCategory.MEMORY and memory)
        ):
            raise ValueError("Select a product or provide memory configuration")
        return self


class GameSettingsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mouse_dpi: int | None = PydanticField(default=None, gt=0, le=2147483647)
    sensitivity: Decimal | None = PydanticField(
        default=None, gt=0, max_digits=18, decimal_places=6, allow_inf_nan=False
    )


class SetupInput(BaseModel):
    operating_system: str | None = PydanticField(
        default=None, min_length=1, max_length=100
    )
    model_config = ConfigDict(extra="forbid")
    hardware: list[HardwareInput] = PydanticField(default_factory=list, max_length=13)
    game_settings: GameSettingsInput = PydanticField(default_factory=GameSettingsInput)

    @model_validator(mode="after")
    def unique_categories(self) -> Self:
        categories = [item.category for item in self.hardware]
        if len(categories) != len(set(categories)):
            raise ValueError("Select only one primary product per category")
        return self


class HardwarePublic(HardwareInput):
    product: ProductPublic | None = None


class GameSettingsPublic(GameSettingsInput):
    edpi: Decimal | None = None


class SetupPublic(BaseModel):
    operating_system: str | None = None
    hardware: list[HardwarePublic]
    game_settings: GameSettingsPublic


class PlayerHardware(SQLModel, table=True):
    __tablename__ = "player_hardware"
    player_steamid64: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("player.steamid64", ondelete="CASCADE"),
            primary_key=True,
        )
    )
    category: ProductCategory = Field(sa_column=Column(String(32), primary_key=True))
    product_id: uuid.UUID | None = Field(
        default=None, foreign_key="products.product.id", index=True
    )
    storage_capacity_unit: Literal["GB", "TB"] = Field(
        default="GB", sa_column=Column(String(2), nullable=False, server_default="GB")
    )
    storage_capacity_gb: int | None = None
    memory_capacity_gb: int | None = None
    memory_type: str | None = None
    memory_speed_mts: int | None = None
    monitor_refresh_hz: Decimal | None = Field(
        default=None, sa_column=Column(Numeric(8, 3))
    )


class PlayerGameSettings(SQLModel, table=True):
    __tablename__ = "player_game_settings"
    __table_args__ = (
        CheckConstraint("mouse_dpi IS NULL OR mouse_dpi > 0"),
        CheckConstraint("sensitivity IS NULL OR sensitivity > 0"),
    )
    player_steamid64: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("player.steamid64", ondelete="CASCADE"),
            primary_key=True,
        )
    )
    operating_system: str | None = Field(default=None, max_length=100)
    mouse_dpi: int | None = None
    sensitivity: Decimal | None = Field(default=None, sa_column=Column(Numeric(18, 6)))


class GearLeaderboardEntry(BaseModel):
    rank: int
    product: ProductPublic
    players: int
    share: float


class GearLeaderboardPublic(BaseModel):
    data: list[GearLeaderboardEntry]
    count: int
    participants: int
