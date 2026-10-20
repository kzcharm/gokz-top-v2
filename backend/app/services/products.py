"""Shared catalog and self-reported setups. Callers own transaction commits."""

import uuid
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func, or_, text
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import col, delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.product import (
    GameSettingsPublic,
    GearLeaderboardEntry,
    GearLeaderboardPublic,
    HardwarePublic,
    PlayerGameSettings,
    PlayerHardware,
    Product,
    ProductAlias,
    ProductAudit,
    ProductCategory,
    ProductCreate,
    ProductPublic,
    ProductsPublic,
    SetupInput,
    SetupPublic,
    normalize_product_text,
)
from app.models.utils import get_datetime_utc


async def lock_catalog(session: AsyncSession) -> None:
    # Serialize short catalog/setup writes, including operator merges. Reads stay unlocked.
    await session.execute(text("SELECT pg_advisory_xact_lock(7481249001)"))


def public_product(product: Product) -> ProductPublic:
    return ProductPublic(
        id=product.id,
        category=product.category,
        brand=product.brand,
        model=product.model,
        community_added=product.verified_at is None,
    )


async def resolve_product(session: AsyncSession, product_id: uuid.UUID) -> Product:
    seen: set[uuid.UUID] = set()
    while product_id not in seen:
        seen.add(product_id)
        product = await session.get(Product, product_id)
        if product is None:
            raise ValueError("Product not found")
        if product.merged_into_id is None:
            return product
        product_id = product.merged_into_id
    raise ValueError("Invalid product merge chain")


async def list_brands(
    session: AsyncSession, category: ProductCategory | None = None
) -> list[str]:
    """Only operator-verified, canonical catalog identities curate shared brands."""
    return sorted(
        set(
            (
                await session.exec(
                    select(Product.brand).where(
                        col(Product.verified_at).is_not(None),
                        *([col(Product.category) == category] if category else []),
                        col(Product.merged_into_id).is_(None),
                    )
                )
            ).all()
        ),
        key=str.casefold,
    )


def record_reference(
    session: AsyncSession, product: Product, body: ProductCreate, creator: int | None
) -> None:
    if body.product_url is not None and creator is not None:
        session.add(
            ProductAudit(
                action="product_reference",
                details={
                    "product_id": str(product.id),
                    "submitted_by": str(creator),
                    "url": str(body.product_url),
                },
            )
        )


async def create_product(
    session: AsyncSession, body: ProductCreate, creator: int | None
) -> Product:
    await lock_catalog(session)
    brand = normalize_product_text(body.brand)
    model = normalize_product_text(body.model)
    curated = await list_brands(session)
    canonical_brand = next(
        (name for name in curated if normalize_product_text(name) == brand), body.brand
    )
    existing = (
        await session.exec(
            select(Product).where(
                col(Product.category) == body.category,
                col(Product.normalized_brand) == brand,
                col(Product.normalized_model) == model,
            )
        )
    ).first()
    if existing:
        canonical = await resolve_product(session, existing.id)
        record_reference(session, canonical, body, creator)
        return canonical
    if creator is not None:
        count = (
            await session.exec(
                select(func.count())
                .select_from(Product)
                .where(
                    col(Product.created_by) == creator,
                    col(Product.created_at) >= get_datetime_utc() - timedelta(hours=24),
                )
            )
        ).one()
        if count >= 20:
            raise PermissionError(
                "You can add up to 20 new products per 24 hours. Please select an existing model or try again later."
            )
    product = Product(
        **body.model_dump(exclude={"product_url", "brand"}),
        brand=canonical_brand,
        normalized_brand=brand,
        normalized_model=model,
        created_by=creator,
    )
    session.add(product)
    await session.flush()
    record_reference(session, product, body, creator)
    return product


def search_condition(query: str) -> ColumnElement[bool]:
    needle = normalize_product_text(query)
    # autoescape treats user '%' and '_' as text rather than wildcards.
    aliases = select(col(ProductAlias.product_id)).where(
        col(ProductAlias.normalized_name).contains(needle, autoescape=True)
    )
    return or_(
        (col(Product.normalized_brand) + " " + col(Product.normalized_model)).contains(
            needle, autoescape=True
        ),
        col(Product.id).in_(aliases),
    )


async def list_products(
    session: AsyncSession, category: ProductCategory, query: str, skip: int, limit: int
) -> ProductsPublic:
    conditions = [
        col(Product.category) == category,
        col(Product.merged_into_id).is_(None),
        search_condition(query),
    ]
    count = (
        await session.exec(select(func.count()).select_from(Product).where(*conditions))
    ).one()
    products = (
        await session.exec(
            select(Product)
            .where(*conditions)
            .order_by(
                col(Product.normalized_brand),
                col(Product.normalized_model),
                col(Product.id),
            )
            .offset(skip)
            .limit(limit)
        )
    ).all()
    return ProductsPublic(data=[public_product(p) for p in products], count=count)


async def read_setup(session: AsyncSession, steamid64: int) -> SetupPublic:
    rows = (
        await session.exec(
            select(PlayerHardware, Product)
            .join(
                Product, col(PlayerHardware.product_id) == col(Product.id), isouter=True
            )
            .where(col(PlayerHardware.player_steamid64) == steamid64)
            .order_by(col(PlayerHardware.category))
        )
    ).all()
    game = await session.get(PlayerGameSettings, steamid64)
    dpi = game.mouse_dpi if game else None
    sensitivity = game.sensitivity if game else None
    return SetupPublic(
        operating_system=game.operating_system if game else None,
        hardware=[
            HardwarePublic(
                **hardware.model_dump(exclude={"player_steamid64"}, warnings=False),
                product=public_product(product) if product else None,
            )
            for hardware, product in rows
        ],
        game_settings=GameSettingsPublic(
            mouse_dpi=dpi,
            sensitivity=sensitivity,
            edpi=Decimal(dpi) * sensitivity
            if dpi is not None and sensitivity is not None
            else None,
        ),
    )


async def replace_setup(
    session: AsyncSession, steamid64: int, body: SetupInput
) -> SetupPublic:
    await lock_catalog(session)
    hardware: list[PlayerHardware] = []
    for item in body.hardware:
        values = item.model_dump()
        if item.product_id is not None:
            product = await resolve_product(session, item.product_id)
            if product.category != item.category:
                raise ValueError("Product does not belong to the selected category")
            values["product_id"] = product.id
        hardware.append(PlayerHardware(player_steamid64=steamid64, **values))
    await session.exec(
        delete(PlayerHardware).where(col(PlayerHardware.player_steamid64) == steamid64)
    )
    session.add_all(hardware)
    game = await session.get(PlayerGameSettings, steamid64)
    if game is None:
        game = PlayerGameSettings(player_steamid64=steamid64)
    game.operating_system = body.operating_system
    game.mouse_dpi = body.game_settings.mouse_dpi
    game.sensitivity = body.game_settings.sensitivity
    session.add(game)
    await session.flush()
    return await read_setup(session, steamid64)


async def gear_leaderboard(
    session: AsyncSession, category: ProductCategory, query: str, skip: int, limit: int
) -> GearLeaderboardPublic:
    usage = (
        select(
            col(PlayerHardware.product_id),
            func.count(func.distinct(col(PlayerHardware.player_steamid64))).label(
                "players"
            ),
        )
        .where(
            col(PlayerHardware.category) == category,
            col(PlayerHardware.product_id).is_not(None),
        )
        .group_by(col(PlayerHardware.product_id))
        .subquery()
    )
    ranked = (
        select(
            col(Product.id).label("product_id"),
            usage.c.players,
            func.row_number()
            .over(
                order_by=(
                    usage.c.players.desc(),
                    col(Product.normalized_brand),
                    col(Product.normalized_model),
                    col(Product.id),
                )
            )
            .label("rank"),
        )
        .join(usage, col(Product.id) == usage.c.product_id)
        .subquery()
    )
    participants = int(
        (await session.exec(select(func.coalesce(func.sum(usage.c.players), 0)))).one()
    )
    condition = search_condition(query)
    count = (
        await session.exec(
            select(func.count())
            .select_from(Product)
            .join(ranked, col(Product.id) == ranked.c.product_id)
            .where(condition)
        )
    ).one()
    rows = (
        await session.exec(
            select(Product, ranked.c.players, ranked.c.rank)
            .join(ranked, col(Product.id) == ranked.c.product_id)
            .where(condition)
            .order_by(ranked.c.rank)
            .offset(skip)
            .limit(limit)
        )
    ).all()
    return GearLeaderboardPublic(
        data=[
            GearLeaderboardEntry(
                rank=rank,
                product=public_product(product),
                players=players,
                share=players / participants * 100,
            )
            for product, players, rank in rows
        ],
        count=count,
        participants=participants,
    )


async def merge_products(
    session: AsyncSession,
    source_id: uuid.UUID,
    target_id: uuid.UUID,
    dry_run: bool = False,
) -> dict[str, object]:
    await lock_catalog(session)
    source = await resolve_product(session, source_id)
    target = await resolve_product(session, target_id)
    if source.category != target.category:
        raise ValueError("Cannot merge products from different categories")
    selections = (
        await session.exec(
            select(PlayerHardware).where(col(PlayerHardware.product_id) == source.id)
        )
    ).all()
    result: dict[str, object] = {
        "source": str(source.id),
        "target": str(target.id),
        "selections": len(selections),
        "dry_run": dry_run,
    }
    if source.id == target.id or dry_run:
        return result
    for selection in selections:
        selection.product_id = target.id
        session.add(selection)
    aliases = (
        await session.exec(
            select(ProductAlias).where(col(ProductAlias.product_id) == source.id)
        )
    ).all()
    target_names = set(
        (
            await session.exec(
                select(col(ProductAlias.normalized_name)).where(
                    col(ProductAlias.product_id) == target.id
                )
            )
        ).all()
    )
    names = {
        normalize_product_text(f"{source.brand} {source.model}"),
        *(alias.normalized_name for alias in aliases),
    }
    for name in names - target_names:
        session.add(ProductAlias(product_id=target.id, normalized_name=name))
    for alias in aliases:
        await session.delete(alias)
    source.merged_into_id = target.id
    session.add(source)
    session.add(ProductAudit(action="merge", details=result))
    await session.flush()
    return result
