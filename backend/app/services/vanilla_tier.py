from __future__ import annotations

import asyncio
import csv
from io import StringIO
from typing import NamedTuple

import httpx
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models import Map


class VanillaTierSyncError(RuntimeError):
    pass


class VanillaTierEntry(NamedTuple):
    tp_tier: int | None
    pro_tier: int | None


_VALID_MAP_PREFIXES = ("kz_", "bkz_", "xc_", "skz_", "vnl_", "kzpro_")


def normalize_vanilla_tier_map_name(value: str) -> str:
    return value.strip().lower()


def _build_sheet_csv_url(*, spreadsheet_id: str, sheet_name: str) -> str:
    encoded_sheet_name = sheet_name.replace(" ", "%20")
    return (
        "https://docs.google.com/spreadsheets/d/"
        f"{spreadsheet_id}/gviz/tq?tqx=out:csv&sheet={encoded_sheet_name}"
    )


def _parse_optional_tier(value: str) -> int | None:
    normalized = value.strip()
    if not normalized:
        return None
    try:
        return int(normalized)
    except ValueError:
        return None


def parse_map_tiers_csv(csv_text: str) -> dict[str, VanillaTierEntry]:
    rows = csv.reader(StringIO(csv_text))
    parsed: dict[str, VanillaTierEntry] = {}
    for row in rows:
        if not row:
            continue
        map_name = normalize_vanilla_tier_map_name(row[0])
        if not map_name or map_name == "map name":
            continue

        tp_tier = _parse_optional_tier(row[1] if len(row) > 1 else "")
        pro_tier = _parse_optional_tier(row[2] if len(row) > 2 else "")
        if tp_tier is None and pro_tier is None:
            continue

        parsed[map_name] = VanillaTierEntry(tp_tier=tp_tier, pro_tier=pro_tier)

    return parsed


def parse_uncompleted_maps_csv(csv_text: str) -> set[str]:
    rows = csv.reader(StringIO(csv_text))
    parsed: set[str] = set()
    for row in rows:
        if not row:
            continue
        map_name = normalize_vanilla_tier_map_name(row[0])
        if not map_name:
            continue
        if map_name in {"feasible maps unfeasible maps", "impossible maps"}:
            continue
        if not map_name.startswith(_VALID_MAP_PREFIXES):
            continue
        parsed.add(map_name)

    return parsed


async def fetch_vanilla_tier_sheet_csv(
    *,
    client: httpx.AsyncClient | None = None,
    sheet_name: str,
) -> str:
    close_client = client is None
    resolved_client = client or httpx.AsyncClient(
        timeout=settings.GLOBALAPI_TIMEOUT_SECONDS,
        trust_env=settings.GLOBALAPI_HTTPX_TRUST_ENV,
    )
    try:
        response = await resolved_client.get(
            _build_sheet_csv_url(
                spreadsheet_id=settings.VANILLATIER_SPREADSHEET_ID,
                sheet_name=sheet_name,
            )
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise VanillaTierSyncError(
            f"Failed to fetch VanillaTier sheet: {sheet_name}"
        ) from exc
    finally:
        if close_client:
            await resolved_client.aclose()

    return response.text


async def load_vanilla_tiers_by_map_id(
    *,
    session: AsyncSession,
    client: httpx.AsyncClient | None = None,
) -> dict[int, VanillaTierEntry]:
    close_client = client is None
    resolved_client = client or httpx.AsyncClient(
        timeout=settings.GLOBALAPI_TIMEOUT_SECONDS,
        trust_env=settings.GLOBALAPI_HTTPX_TRUST_ENV,
    )
    try:
        map_tiers_csv, uncompleted_maps_csv = await asyncio.gather(
            fetch_vanilla_tier_sheet_csv(
                client=resolved_client,
                sheet_name=settings.VANILLATIER_MAP_TIERS_SHEET_NAME,
            ),
            fetch_vanilla_tier_sheet_csv(
                client=resolved_client,
                sheet_name=settings.VANILLATIER_UNCOMPLETED_MAPS_SHEET_NAME,
            ),
        )
    finally:
        if close_client:
            await resolved_client.aclose()

    tiers_by_map_name = parse_map_tiers_csv(map_tiers_csv)
    status_only_map_names = parse_uncompleted_maps_csv(uncompleted_maps_csv) - set(
        tiers_by_map_name.keys()
    )

    candidate_map_names = [*tiers_by_map_name.keys(), *status_only_map_names]
    if not candidate_map_names:
        return {}

    map_rows = (
        await session.exec(
            select(Map.id, Map.name).where(col(Map.name).in_(candidate_map_names))
        )
    ).all()

    normalized_local_map_ids = {
        normalize_vanilla_tier_map_name(map_name): map_id for map_id, map_name in map_rows
    }

    resolved: dict[int, VanillaTierEntry] = {}
    for map_name, entry in tiers_by_map_name.items():
        map_id = normalized_local_map_ids.get(map_name)
        if map_id is None:
            continue
        resolved[map_id] = entry

    for map_name in status_only_map_names:
        map_id = normalized_local_map_ids.get(map_name)
        if map_id is None:
            continue
        resolved[map_id] = VanillaTierEntry(tp_tier=0, pro_tier=0)

    return resolved
