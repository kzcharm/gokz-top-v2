import json
from collections import Counter
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
import typer
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import product_cli
from app.models.product import Product, ProductAlias, ProductAudit, ProductCategory
from app.services import products


@pytest.mark.asyncio
async def test_catalog_import_correction_and_audit(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    @asynccontextmanager
    async def session():
        yield db

    monkeypatch.setattr(product_cli, "async_session_maker", session)
    path = tmp_path / "catalog.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "products": [
                    {
                        "category": "mouse",
                        "brand": "Catalog Test",
                        "model": "One",
                        "verified": True,
                        "source_url": "https://example.com/one",
                        "aliases": ["Old One", "Old  One"],
                    },
                    {
                        "category": "mouse",
                        "brand": "Catalog Test",
                        "model": "Two",
                        "verified": False,
                    },
                ],
            }
        )
    )
    await product_cli.import_manifest(path, False)
    await product_cli.import_manifest(path, False)
    found = await products.list_products(
        db, ProductCategory.MOUSE, "Catalog Test", 0, 50
    )
    assert found.count == 2
    one, two = found.data
    assert not one.community_added and two.community_added
    aliases = (
        await db.exec(
            select(ProductAlias).where(col(ProductAlias.product_id) == one.id)
        )
    ).all()
    assert len(aliases) == 1
    unverified = await product_cli.inspect_products(True)
    assert any(row["id"] == str(two.id) for row in unverified)
    assert all(row["id"] != str(one.id) for row in unverified)
    result = await product_cli.verify_identity(
        one.id, "https://example.com/corrected", None, "Corrected One", True
    )
    assert result["dry_run"] is True
    assert (await db.get(Product, one.id)).model == "One"
    await product_cli.verify_identity(
        one.id, "https://example.com/corrected", None, "Corrected One", False
    )
    assert (await db.get(Product, one.id)).model == "Corrected One"
    assert (
        await products.list_products(
            db, ProductCategory.MOUSE, "Catalog Test One", 0, 50
        )
    ).count == 1
    with pytest.raises(typer.BadParameter):
        await product_cli.verify_identity(
            two.id, "https://example.com", None, "Corrected One", False
        )
    audits = (
        await db.exec(select(ProductAudit).where(col(ProductAudit.action) == "verify"))
    ).all()
    assert any(row.details["id"] == str(one.id) for row in audits)


@pytest.mark.asyncio
async def test_catalog_import_dry_run(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    @asynccontextmanager
    async def session():
        yield db

    monkeypatch.setattr(product_cli, "async_session_maker", session)
    path = tmp_path / "catalog.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "products": [
                    {"category": "cpu", "brand": "Dry Run", "model": "No Write"}
                ],
            }
        )
    )
    await product_cli.import_manifest(path, True)
    assert (
        await products.list_products(db, ProductCategory.CPU, "Dry Run", 0, 10)
    ).count == 0


def test_catalog_covers_all_categories_with_distinct_sourced_models() -> None:
    path = Path(product_cli.__file__).parent / "data" / "products.v1.json"
    manifest = json.loads(path.read_text())
    entries = manifest["products"]
    assert len(entries) >= 2400
    counts = Counter(p["category"] for p in entries)
    assert set(counts) == {category.value for category in ProductCategory}
    assert min(counts.values()) >= 10
    assert len({(p["category"], p["brand"], p["model"]) for p in entries}) == len(
        entries
    )
    assert all(
        p["source_url"].startswith("https://") and p["researched_on"] for p in entries
    )


@pytest.mark.asyncio
async def test_catalog_invalid_references_and_merge_chain(db: AsyncSession) -> None:
    import uuid

    from pydantic import ValidationError

    from app.models.product import HardwareInput, ProductCreate

    with pytest.raises(ValueError, match="not found"):
        await products.resolve_product(db, uuid.uuid7())
    first = await products.create_product(
        db, ProductCreate(category="mouse", brand="Chain", model="A"), None
    )
    second = await products.create_product(
        db, ProductCreate(category="mouse", brand="Chain", model="B"), None
    )
    first.merged_into_id = second.id
    second.merged_into_id = first.id
    db.add(first)
    db.add(second)
    await db.flush()
    with pytest.raises(ValueError, match="merge chain"):
        await products.resolve_product(db, first.id)
    with pytest.raises(ValidationError):
        ProductCreate.model_validate(
            {"category": "mouse", "brand": 123, "model": "Test"}
        )
    with pytest.raises(ValidationError):
        HardwareInput(category="mouse", product_id=first.id, monitor_refresh_hz="144")
    with pytest.raises(ValidationError):
        HardwareInput(category="memory")


@pytest.mark.asyncio
async def test_launch_catalog_import_and_regional_alias_searches(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    @asynccontextmanager
    async def session():
        yield db

    monkeypatch.setattr(product_cli, "async_session_maker", session)
    manifest = Path(product_cli.__file__).parent / "data" / "products.v1.json"
    await product_cli.import_manifest(manifest, False)
    await product_cli.import_manifest(manifest, False)
    for query, expected in (
        ("GPW2", "PRO X SUPERLIGHT"),
        ("GPW 2", "PRO X SUPERLIGHT"),
        ("ｇｐｗ　２", "PRO X SUPERLIGHT"),
        ("GPW3", "PRO X SUPERLIGHT 2"),
        ("GPX 2", "PRO X SUPERLIGHT 2"),
    ):
        result = await products.list_products(db, ProductCategory.MOUSE, query, 0, 20)
        assert result.count == 1
        assert result.data[0].model == expected

    for category, query, expected in (
        (ProductCategory.KEYBOARD, "NuPhy Halo 75 V2", "Halo75 V2"),
        (ProductCategory.KEYBOARD, "NuPhy Air75 V2", "Air75 V2"),
        (ProductCategory.KEYBOARD, "狼蛛 F75", "F75"),
        (ProductCategory.KEYBOARD, "阿米洛 Minilo75 Pro", "Minilo75 Pro"),
        (ProductCategory.MOUSE, "VXE R1 Pro Max", "R1 Pro Max"),
        (ProductCategory.MOUSE, "达尔优 A950 Pro", "A950 Pro"),
        (ProductCategory.CPU, "R7 5800X", "Ryzen 7 5800X"),
        (ProductCategory.CPU, "R5 7500F", "Ryzen 5 7500F"),
        (ProductCategory.GPU, "RTX3060", "GeForce RTX 3060"),
        (ProductCategory.GPU, "GTX 1650", "GeForce GTX 1650"),
        (ProductCategory.GPU, "RX 580 2048SP", "Radeon RX 580 2048SP"),
        (ProductCategory.CPU, "i7-8700K", "Core i7-8700K"),
        (ProductCategory.CPU, "R5 3600", "Ryzen 5 3600"),
        (ProductCategory.COOLING, "利民 PA120 SE", "Peerless Assassin 120 SE"),
        (ProductCategory.POWER_SUPPLY, "海韵 FOCUS GX 850W", "FOCUS GX 850W"),
        (ProductCategory.STORAGE, "SN850X", "WD_BLACK SN850X"),
        (ProductCategory.MONITOR, "24G2", "24G2"),
    ):
        result = await products.list_products(db, category, query, 0, 100)
        assert expected in [item.model for item in result.data]
        assert all(item.category == category for item in result.data)
    assert "NuPhy" in await products.list_brands(db, ProductCategory.KEYBOARD)
    assert "AULA" in await products.list_brands(db, ProductCategory.KEYBOARD)
    assert "VXE" in await products.list_brands(db, ProductCategory.MOUSE)
    assert "VXE" not in await products.list_brands(db, ProductCategory.CPU)


@pytest.mark.asyncio
async def test_curated_brands_references_and_category_scope(db: AsyncSession) -> None:
    from pydantic import ValidationError

    from app.models.product import ProductCreate
    from app.models.utils import get_datetime_utc

    mouse = await products.create_product(
        db,
        ProductCreate(category="mouse", brand="CuratedBrand", model="Shared Model"),
        None,
    )
    mouse.verified_at = get_datetime_utc()
    db.add(mouse)
    await db.flush()
    headset = await products.create_product(
        db,
        ProductCreate(
            category="headset", brand="UnreviewedBrand", model="Shared Model"
        ),
        None,
    )
    assert "CuratedBrand" in await products.list_brands(db, ProductCategory.MOUSE)
    assert "CuratedBrand" not in await products.list_brands(
        db, ProductCategory.KEYBOARD
    )
    assert "UnreviewedBrand" not in await products.list_brands(db)
    matches = await products.list_products(
        db, ProductCategory.MOUSE, "Shared Model", 0, 100
    )
    assert mouse.id in [p.id for p in matches.data]
    assert headset.id not in [p.id for p in matches.data]
    reused = await products.create_product(
        db,
        ProductCreate(
            category="mouse",
            brand="curatedbrand",
            model="Shared Model",
            product_url="https://example.com/product",
        ),
        76561198000000001,
    )
    assert reused.id == mouse.id
    await db.flush()
    references = (
        await db.exec(
            select(ProductAudit).where(ProductAudit.action == "product_reference")
        )
    ).all()
    assert any(
        r.details.get("product_id") == str(mouse.id)
        and r.details.get("url") == "https://example.com/product"
        for r in references
    )
    for url in (
        "javascript:alert(1)",
        "ftp://example.com/a",
        "not a URL",
        "https://example.com/" + "a" * 2048,
    ):
        with pytest.raises(ValidationError):
            ProductCreate(
                category="mouse", brand="Brand", model="Model", product_url=url
            )


def test_catalog_coverage_report_matches_categories_and_steam_gpu_models() -> None:
    folder = Path(product_cli.__file__).parent / "data"
    manifest = json.loads((folder / "products.v1.json").read_text())
    coverage = json.loads((folder / "products.coverage.v4.json").read_text())
    entries = manifest["products"]
    counts = Counter(entry["category"] for entry in entries)
    assert coverage["after_total"] == len(entries)
    assert coverage["added"] == len(entries) - coverage["before_total"]
    assert {
        key: value["after"] for key, value in coverage["categories"].items()
    } == counts
    for category, minimum in {
        "gpu": 200,
        "monitor": 130,
        "power_supply": 140,
        "storage": 70,
        "cpu": 300,
        "mouse": 250,
        "mouse_pad": 80,
    }.items():
        assert counts[category] >= minimum
    reference = coverage["steam_reference"]
    assert reference["url"] in manifest["usage_sources"]
    assert reference["survey_month"] == "September 2026"
    assert reference["missing_models"] == []
    assert reference["covered_models"] == len(reference["models"]) == 81
    gpu_names = {
        entry["brand"] + " " + entry["model"]
        for entry in entries
        if entry["category"] == "gpu"
    }
    assert set(reference["models"]) <= gpu_names
    assert "NVIDIA GeForce RTX 3060" in gpu_names
    assert "NVIDIA GeForce RTX 4090 Founders Edition" in gpu_names
    assert "NVIDIA GeForce RTX 4090" in gpu_names
    assert "AMD Radeon RX 580 2048SP" in gpu_names
    assert "AMD Radeon Graphics" not in gpu_names
    assert "Intel Arc Graphics" not in gpu_names
    for entry in entries:
        if entry.get("catalog_revision") == 4 and entry["brand"] == "DeepCool":
            if entry["category"] == "cooling":
                assert "/Cooling/fans/" not in entry["source_url"]
                assert "/Cooling/laptopcoolers/" not in entry["source_url"]
