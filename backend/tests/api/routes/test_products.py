import asyncio
import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from pydantic import ValidationError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import async_session_maker
from app.models.product import (
    GameSettingsInput,
    HardwareInput,
    PlayerHardware,
    Product,
    ProductAlias,
    ProductCategory,
    ProductCreate,
    SetupInput,
)
from app.services import products
from tests.utils.user import authentication_token_from_steamid


@pytest.mark.parametrize(
    "values",
    [
        {"mouse_dpi": 0},
        {"mouse_dpi": -1},
        {"mouse_dpi": 1.5},
        {"sensitivity": "NaN"},
        {"sensitivity": "Infinity"},
        {"sensitivity": "-1"},
        {"sensitivity": "0"},
        {"sensitivity": "0.1234567"},
        {"edpi": 1000},
    ],
)
def test_game_settings_validation(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        GameSettingsInput.model_validate(values)


@pytest.mark.asyncio
async def test_setup_roundtrip_and_ownership(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = 76561198000000451
    headers = await authentication_token_from_steamid(
        client=client, steamid64=owner, db=db
    )
    other = await authentication_token_from_steamid(
        client=client, steamid64=76561198000000452, db=db
    )
    created = await client.post(
        "/v1/products",
        headers=headers,
        json={"category": "mouse", "brand": " Test ", "model": "  Model   One "},
    )
    assert created.status_code == 200
    product = created.json()
    assert product["brand"] == "Test" and product["model"] == "Model One"
    assert product["community_added"] is True
    body = {
        "operating_system": "Windows 11",
        "hardware": [
            {"category": "mouse", "product_id": product["id"]},
            {"category": "memory", "memory_capacity_gb": 32, "memory_type": "DDR5"},
            {
                "category": "storage",
                "storage_capacity_gb": 2000,
                "storage_capacity_unit": "TB",
            },
        ],
        "game_settings": {"mouse_dpi": 800, "sensitivity": "1.25"},
    }
    saved = await client.put("/v1/me/setup", headers=headers, json=body)
    assert saved.status_code == 200, saved.text
    assert Decimal(saved.json()["game_settings"]["edpi"]) == 1000
    public = await client.get(f"/v1/players/{owner}/setup")
    assert public.status_code == 200
    assert len(public.json()["hardware"]) == 3
    assert public.json()["operating_system"] == "Windows 11"
    assert (
        next(
            item for item in public.json()["hardware"] if item["category"] == "storage"
        )["storage_capacity_unit"]
        == "TB"
    )
    assert (
        next(
            item for item in public.json()["hardware"] if item["category"] == "storage"
        )["storage_capacity_gb"]
        == 2000
    )
    assert (await client.get("/v1/me/setup", headers=other)).json()["hardware"] == []
    assert (await client.put("/v1/me/setup", json=body)).status_code == 401
    assert (
        await client.post(
            "/v1/products", json={"category": "mouse", "brand": "X", "model": "Y"}
        )
    ).status_code == 401
    assert (
        await client.put(
            "/v1/me/setup", headers=headers, json={"player_steamid64": 123}
        )
    ).status_code == 422
    cleared = await client.put("/v1/me/setup", headers=headers, json={})
    assert cleared.status_code == 200
    assert cleared.json()["hardware"] == []
    assert cleared.json()["operating_system"] is None
    assert cleared.json()["game_settings"]["edpi"] is None


@pytest.mark.asyncio
async def test_duplicates_aliases_and_limit(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await authentication_token_from_steamid(
        client=client, steamid64=76561198000000453, db=db
    )
    payload = {"category": "mouse", "brand": "Ｂrand", "model": " Model One "}
    first = await client.post("/v1/products", headers=headers, json=payload)
    second = await client.post(
        "/v1/products",
        headers=headers,
        json={**payload, "brand": "brand", "model": "model   one"},
    )
    assert first.json()["id"] == second.json()["id"]
    db.add(
        ProductAlias(
            product_id=uuid.UUID(first.json()["id"]), normalized_name="short alias"
        )
    )
    await db.flush()
    response = await client.get(
        "/v1/products", params={"category": "mouse", "q": "short alias"}
    )
    assert response.json()["count"] == 1
    for i in range(19):
        assert (
            await client.post(
                "/v1/products", headers=headers, json={**payload, "model": f"Extra {i}"}
            )
        ).status_code == 200
    assert (
        await client.post(
            "/v1/products", headers=headers, json={**payload, "model": "Excess"}
        )
    ).status_code == 429
    assert (
        await client.post("/v1/products", headers=headers, json=payload)
    ).status_code == 200


@pytest.mark.asyncio
async def test_category_mismatch_is_atomic(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await authentication_token_from_steamid(
        client=client, steamid64=76561198000000454, db=db
    )
    item = (
        await client.post(
            "/v1/products",
            headers=headers,
            json={"category": "mouse", "brand": "Atomic", "model": "One"},
        )
    ).json()
    assert (
        await client.put(
            "/v1/me/setup", headers=headers, json={"game_settings": {"mouse_dpi": 400}}
        )
    ).status_code == 200
    bad = await client.put(
        "/v1/me/setup",
        headers=headers,
        json={"hardware": [{"category": "gpu", "product_id": item["id"]}]},
    )
    assert bad.status_code == 422
    assert (await client.get("/v1/me/setup", headers=headers)).json()["game_settings"][
        "mouse_dpi"
    ] == 400
    unknown = await client.put(
        "/v1/me/setup",
        headers=headers,
        json={"hardware": [{"category": "mouse", "product_id": str(uuid.uuid7())}]},
    )
    assert unknown.status_code == 422


@pytest.mark.asyncio
async def test_ranking_merge_and_stale_ids(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = [
        await authentication_token_from_steamid(
            client=client, steamid64=76561198000000460 + i, db=db
        )
        for i in range(3)
    ]
    a = await products.create_product(
        db,
        ProductCreate(category=ProductCategory.MONITOR, brand="Brand", model="A"),
        None,
    )
    b = await products.create_product(
        db,
        ProductCreate(category=ProductCategory.MONITOR, brand="Brand", model="B"),
        None,
    )
    for i, auth in enumerate(headers):
        response = await client.put(
            "/v1/me/setup",
            headers=auth,
            json={
                "hardware": [
                    {
                        "category": "monitor",
                        "product_id": str(a.id if i < 2 else b.id),
                        "monitor_refresh_hz": "239.76",
                    }
                ]
            },
        )
        assert response.status_code == 200, response.text
    ranking = (
        await client.get(
            "/v1/leaderboards/gear",
            params={"category": "monitor", "q": "B", "limit": 1},
        )
    ).json()
    assert ranking["participants"] == 3
    assert ranking["count"] == 2  # brand contains B
    filtered = (
        await client.get(
            "/v1/leaderboards/gear", params={"category": "monitor", "q": "Brand B"}
        )
    ).json()
    assert filtered["count"] == 1 and filtered["data"][0]["rank"] == 2
    assert filtered["data"][0]["share"] == pytest.approx(100 / 3)
    await products.merge_products(db, b.id, a.id, dry_run=True)
    assert (await products.resolve_product(db, b.id)).id == b.id
    await products.merge_products(db, b.id, a.id)
    setup = await products.read_setup(db, 76561198000000462)
    assert setup.hardware[0].product_id == a.id
    assert setup.hardware[0].monitor_refresh_hz == Decimal("239.760")
    await products.replace_setup(
        db,
        76561198000000462,
        SetupInput(
            hardware=[HardwareInput(category=ProductCategory.MONITOR, product_id=b.id)]
        ),
    )
    ranking_after = await products.gear_leaderboard(
        db, ProductCategory.MONITOR, "", 0, 20
    )
    assert ranking_after.participants == 3 and ranking_after.count == 1
    assert ranking_after.data[0].share == 100
    assert (
        await products.list_products(db, ProductCategory.MONITOR, "Brand B", 0, 20)
    ).data[0].id == a.id
    other = await products.create_product(
        db, ProductCreate(category=ProductCategory.CPU, brand="CPU", model="One"), None
    )
    with pytest.raises(ValueError, match="different categories"):
        await products.merge_products(db, other.id, a.id)


@pytest.mark.asyncio
async def test_concurrent_creation_uses_one_identity() -> None:
    body = ProductCreate(
        category=ProductCategory.MOUSE, brand="Concurrent", model=str(uuid.uuid7())
    )

    async def create() -> uuid.UUID:
        async with async_session_maker() as session:
            product = await products.create_product(session, body, None)
            product_id = product.id
            await session.commit()
            return product_id

    identities = await asyncio.gather(create(), create())
    assert identities[0] == identities[1]
    async with async_session_maker() as session:
        product = await session.get(Product, identities[0])
        assert product
        await session.delete(product)
        await session.commit()


def test_duplicate_categories_and_configuration_validation() -> None:
    with pytest.raises(ValidationError):
        SetupInput(
            hardware=[
                HardwareInput(category=ProductCategory.MEMORY, memory_capacity_gb=32)
            ]
            * 2
        )
    with pytest.raises(ValidationError):
        HardwareInput(category=ProductCategory.MOUSE, memory_capacity_gb=32)
    with pytest.raises(ValidationError):
        ProductCreate(category=ProductCategory.MOUSE, brand=" ", model="x")


@pytest.mark.parametrize(
    "values",
    [
        {"category": "storage", "storage_capacity_gb": 0},
        {"category": "storage", "storage_capacity_gb": -1},
        {"category": "storage", "storage_capacity_gb": 1.25},
        {"category": "memory", "storage_capacity_gb": 1000},
    ],
)
def test_storage_configuration_validation(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        HardwareInput.model_validate(values)


@pytest.mark.asyncio
async def test_multiple_disks_monitor_size_and_timestamps(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = 76561198000000480
    headers = await authentication_token_from_steamid(
        client=client, steamid64=owner, db=db
    )
    monitor = await products.create_product(
        db,
        ProductCreate(category=ProductCategory.MONITOR, brand="Display", model="27"),
        None,
    )
    body = {
        "hardware": [
            {
                "category": "storage",
                "storage_capacity_gb": 2000,
                "storage_capacity_unit": "TB",
            },
            {
                "category": "monitor",
                "product_id": str(monitor.id),
                "monitor_size_inches": "27.5",
                "monitor_refresh_hz": "239.76",
            },
            {"category": "storage", "storage_capacity_gb": 512},
        ]
    }
    saved = await client.put("/v1/me/setup", headers=headers, json=body)
    assert saved.status_code == 200, saved.text
    setup = saved.json()
    assert "created_at" not in setup and "updated_at" not in setup
    assert [
        item["storage_capacity_gb"]
        for item in setup["hardware"]
        if item["category"] == "storage"
    ] == [2000, 512]
    assert Decimal(setup["hardware"][1]["monitor_size_inches"]) == Decimal("27.5")
    stored = await db.get(PlayerHardware, owner)
    assert stored and stored.selections[1]["product_id"] == str(monitor.id)
    assert stored.selections[1]["monitor_size_inches"] == "27.5"
    created_at, updated_at = stored.created_at, stored.updated_at
    assert created_at and updated_at
    assert (await client.get(f"/v1/players/{owner}/setup")).json() == setup
    updated = await client.put(
        "/v1/me/setup", headers=headers, json={"game_settings": {"mouse_dpi": 800}}
    )
    await db.refresh(stored)
    assert stored.created_at == created_at
    assert stored.updated_at > updated_at
    assert "created_at" not in updated.json() and "updated_at" not in updated.json()
    assert updated.json()["hardware"] == []
    invalid = await client.put(
        "/v1/me/setup",
        headers=headers,
        json={
            "hardware": [
                {"category": "storage", "storage_capacity_gb": 1000},
                {"category": "monitor", "product_id": str(uuid.uuid7())},
            ]
        },
    )
    assert invalid.status_code == 422
    assert (await client.get("/v1/me/setup", headers=headers)).json() == updated.json()


@pytest.mark.asyncio
async def test_disk_ranking_and_merge_count_distinct_players(
    client: AsyncClient, db: AsyncSession
) -> None:
    owners = [76561198000000481, 76561198000000482]
    headers = [
        await authentication_token_from_steamid(client=client, steamid64=owner, db=db)
        for owner in owners
    ]
    a = await products.create_product(
        db,
        ProductCreate(category=ProductCategory.STORAGE, brand="Disk", model="A"),
        None,
    )
    b = await products.create_product(
        db,
        ProductCreate(category=ProductCategory.STORAGE, brand="Disk", model="B"),
        None,
    )
    for auth, entries in zip(headers, [[a, a, b], [b]], strict=True):
        result = await client.put(
            "/v1/me/setup",
            headers=auth,
            json={
                "hardware": [
                    {
                        "category": "storage",
                        "product_id": str(product.id),
                        "storage_capacity_gb": 1000 + index,
                    }
                    for index, product in enumerate(entries)
                ]
            },
        )
        assert result.status_code == 200, result.text
    ranking = await products.gear_leaderboard(db, ProductCategory.STORAGE, "", 0, 20)
    assert ranking.participants == 2
    assert [
        (entry.product.id, entry.players, entry.share) for entry in ranking.data
    ] == [(b.id, 2, 100), (a.id, 1, 50)]
    assert (await products.merge_products(db, a.id, b.id, dry_run=True))[
        "selections"
    ] == 2
    stored = await db.get(PlayerHardware, owners[0])
    assert stored
    updated_at = stored.updated_at
    await products.merge_products(db, a.id, b.id)
    after = await products.read_setup(db, owners[0])
    assert len(after.hardware) == 3 and all(
        item.product_id == b.id for item in after.hardware
    )
    assert [item.storage_capacity_gb for item in after.hardware] == [1000, 1001, 1002]
    await db.refresh(stored)
    assert stored.updated_at == updated_at
    ranking = await products.gear_leaderboard(db, ProductCategory.STORAGE, "", 0, 20)
    assert ranking.participants == 2 and ranking.count == 1
    assert ranking.data[0].players == 2 and ranking.data[0].share == 100


@pytest.mark.parametrize("value", ["0", "-1", "200.01", "27.123", "NaN", "Infinity"])
def test_monitor_size_validation(value: str) -> None:
    with pytest.raises(ValidationError):
        HardwareInput(
            category=ProductCategory.MONITOR,
            product_id=uuid.uuid7(),
            monitor_size_inches=Decimal(value),
        )


def test_monitor_size_requires_monitor_category() -> None:
    with pytest.raises(ValidationError):
        HardwareInput(
            category=ProductCategory.MOUSE,
            product_id=uuid.uuid7(),
            monitor_size_inches=Decimal("27"),
        )
