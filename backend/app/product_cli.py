"""Operator-only catalog maintenance; no public approval workflow."""

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from sqlalchemy import func
from sqlmodel import col, select

from app.core.db import async_session_maker
from app.models.product import (
    PlayerHardware,
    Product,
    ProductAlias,
    ProductAudit,
    ProductCreate,
    normalize_product_text,
)
from app.models.utils import get_datetime_utc
from app.services import products

app = typer.Typer(help="Import, inspect, and maintain the shared hardware catalog.")
console = Console()


async def import_manifest(path: Path, dry_run: bool) -> dict[str, object]:
    manifest = json.loads(path.read_text())
    entries = manifest["products"]
    parsed = [
        (
            entry,
            ProductCreate.model_validate(
                {k: entry[k] for k in ("category", "brand", "model")}
            ),
        )
        for entry in entries
    ]
    async with async_session_maker() as session:
        for entry, body in parsed:
            product = await products.create_product(session, body, None)
            product.source_url = entry.get("source_url")
            if entry.get("verified"):
                product.verified_at = get_datetime_utc()
            session.add(product)
            existing = set(
                (
                    await session.exec(
                        select(col(ProductAlias.normalized_name)).where(
                            col(ProductAlias.product_id) == product.id
                        )
                    )
                ).all()
            )
            for alias in entry.get("aliases", []):
                normalized = normalize_product_text(alias)
                if normalized and normalized not in existing:
                    session.add(
                        ProductAlias(product_id=product.id, normalized_name=normalized)
                    )
                    existing.add(normalized)
        result: dict[str, object] = {
            "products": len(entries),
            "dry_run": dry_run,
            "manifest": str(path),
            "version": manifest["version"],
        }
        session.add(ProductAudit(action="import", details=result))
        if dry_run:
            await session.rollback()
        else:
            await session.commit()
        return result


@app.command("import")
def import_products(manifest: Path, dry_run: bool = False) -> None:
    """Idempotently import a versioned seed manifest (does not fetch images)."""
    console.print(asyncio.run(import_manifest(manifest, dry_run)))


async def inspect_products(unverified: bool) -> list[dict[str, Any]]:
    async with async_session_maker() as session:
        statement = (
            select(Product, func.count(col(PlayerHardware.player_steamid64)))
            .join(
                PlayerHardware,
                col(PlayerHardware.product_id) == col(Product.id),
                isouter=True,
            )
            .where(col(Product.merged_into_id).is_(None))
            .group_by(col(Product.id))
            .order_by(
                func.count(col(PlayerHardware.player_steamid64)).desc(),
                col(Product.brand),
                col(Product.model),
            )
        )
        if unverified:
            statement = statement.where(col(Product.verified_at).is_(None))
        rows = (await session.exec(statement)).all()
        return [
            {
                "id": str(p.id),
                "category": p.category,
                "brand": p.brand,
                "model": p.model,
                "players": count,
                "source_url": p.source_url,
            }
            for p, count in rows
        ]


@app.command("list")
def list_products(unverified: bool = False) -> None:
    """List canonical models, ordered by current usage."""
    console.print_json(data=asyncio.run(inspect_products(unverified)))


@app.command("merge")
def merge_products(source: uuid.UUID, target: uuid.UUID, dry_run: bool = False) -> None:
    """Merge exact duplicate identities while retaining aliases and setup details."""

    async def run() -> dict[str, object]:
        async with async_session_maker() as session:
            result = await products.merge_products(session, source, target, dry_run)
            if not dry_run:
                await session.commit()
            return result

    console.print(asyncio.run(run()))


@app.command("verify")
def verify_product(
    product_id: uuid.UUID,
    source_url: str,
    brand: str | None = None,
    model: str | None = None,
    dry_run: bool = False,
) -> None:
    """Verify/correct an identity against its manufacturer source."""

    console.print(
        asyncio.run(verify_identity(product_id, source_url, brand, model, dry_run))
    )


async def verify_identity(
    product_id: uuid.UUID,
    source_url: str,
    brand: str | None,
    model: str | None,
    dry_run: bool,
) -> dict[str, object]:
    async with async_session_maker() as session:
        await products.lock_catalog(session)
        product = await products.resolve_product(session, product_id)
        body = ProductCreate(
            category=product.category,
            brand=brand or product.brand,
            model=model or product.model,
        )
        normalized_brand, normalized_model = (
            normalize_product_text(body.brand),
            normalize_product_text(body.model),
        )
        duplicate = (
            await session.exec(
                select(Product).where(
                    col(Product.category) == body.category,
                    col(Product.normalized_brand) == normalized_brand,
                    col(Product.normalized_model) == normalized_model,
                    col(Product.id) != product.id,
                )
            )
        ).first()
        if duplicate:
            raise typer.BadParameter(
                "That identity exists. Use products merge instead."
            )
        result: dict[str, object] = {
            "id": str(product.id),
            "before": {"brand": product.brand, "model": product.model},
            "after": body.model_dump(mode="json"),
            "source_url": source_url,
            "dry_run": dry_run,
        }
        if not dry_run:
            old_name = normalize_product_text(f"{product.brand} {product.model}")
            existing = (
                await session.exec(
                    select(ProductAlias).where(
                        col(ProductAlias.product_id) == product.id,
                        col(ProductAlias.normalized_name) == old_name,
                    )
                )
            ).first()
            if existing is None:
                session.add(
                    ProductAlias(product_id=product.id, normalized_name=old_name)
                )
            product.brand, product.model = body.brand, body.model
            product.normalized_brand, product.normalized_model = (
                normalized_brand,
                normalized_model,
            )
            product.verified_at = get_datetime_utc()
            product.source_url = source_url
            session.add(product)
            session.add(ProductAudit(action="verify", details=result))
            await session.commit()
        return result


async def inspect_references(skip: int, limit: int) -> list[dict[str, object]]:
    async with async_session_maker() as session:
        rows = (
            await session.exec(
                select(ProductAudit)
                .where(ProductAudit.action == "product_reference")
                .order_by(
                    col(ProductAudit.created_at).desc(), col(ProductAudit.id).desc()
                )
                .offset(skip)
                .limit(limit)
            )
        ).all()
        result: list[dict[str, object]] = []
        for row in rows:
            product = await products.resolve_product(
                session, uuid.UUID(str(row.details["product_id"]))
            )
            result.append(
                {
                    "audit_id": str(row.id),
                    "submitted_at": row.created_at.isoformat(),
                    **row.details,
                    "canonical_product_id": str(product.id),
                    "category": product.category,
                    "brand": product.brand,
                    "model": product.model,
                }
            )
        return result


@app.command("references")
def references(
    skip: int = typer.Option(0, min=0),
    limit: int = typer.Option(100, min=1, max=1000),
) -> None:
    """List submitted product links for manual review, newest first."""
    console.print_json(data=asyncio.run(inspect_references(skip, limit)))
