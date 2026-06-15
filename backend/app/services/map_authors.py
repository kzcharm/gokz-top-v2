from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy import or_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Map, Player, get_datetime_utc

KZ_MAP_INFO_GLOBAL_URL = (
    "https://raw.githubusercontent.com/zer0k-z/kz-map-info/master/"
    "MapsWithMappers_Global.json"
)
STEAMID64_PATTERN = re.compile(r"^\d{17}$")


@dataclass(frozen=True, slots=True)
class MapAuthorSeedResult:
    processed: int
    matched: int
    updated: int
    skipped: int


@dataclass(frozen=True, slots=True)
class ParsedKzMapInfoAuthors:
    map_id: int | None
    map_name: str
    authors: list[str]
    no_steamid_names: list[str]


def _split_author_text(value: Any) -> list[str]:
    if not isinstance(value, str):
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def _dedupe_preserving_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def normalize_steamid64_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        candidates = _split_author_text(value)
    elif isinstance(value, list):
        candidates = []
        for item in value:
            if isinstance(item, str):
                candidates.extend(_split_author_text(item))
            elif item is not None:
                candidates.append(str(item).strip())
    else:
        return []
    return _dedupe_preserving_order(
        [candidate for candidate in candidates if STEAMID64_PATTERN.fullmatch(candidate)]
    )


def normalize_name_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        candidates = _split_author_text(value)
    elif isinstance(value, list):
        candidates = []
        for item in value:
            if isinstance(item, str):
                candidates.extend(_split_author_text(item))
    else:
        return []
    return _dedupe_preserving_order(
        [
            candidate
            for candidate in candidates
            if not STEAMID64_PATTERN.fullmatch(candidate)
        ]
    )


def normalize_author_fields(
    *,
    authors: Any = None,
    no_steamid_names: Any = None,
) -> tuple[list[str], list[str]]:
    steamid_authors = normalize_steamid64_list(authors)
    name_only_authors = normalize_name_list(no_steamid_names)
    name_only_authors.extend(normalize_name_list(authors))
    return (
        _dedupe_preserving_order(steamid_authors),
        _dedupe_preserving_order(name_only_authors),
    )


def merge_author_fields(
    *,
    existing_authors: Any = None,
    existing_no_steamid_names: Any = None,
    incoming_authors: Any = None,
    incoming_no_steamid_names: Any = None,
) -> tuple[list[str], list[str]]:
    existing_steamids, existing_names = normalize_author_fields(
        authors=existing_authors,
        no_steamid_names=existing_no_steamid_names,
    )
    incoming_steamids, incoming_names = normalize_author_fields(
        authors=incoming_authors,
        no_steamid_names=incoming_no_steamid_names,
    )
    return (
        _dedupe_preserving_order([*existing_steamids, *incoming_steamids]),
        _dedupe_preserving_order([*existing_names, *incoming_names]),
    )


async def ensure_author_players_exist(
    *,
    session: AsyncSession,
    author_steamid64s: list[str],
) -> None:
    normalized_steamid64s = normalize_steamid64_list(author_steamid64s)
    if not normalized_steamid64s:
        return

    now = get_datetime_utc()
    player_table = Player.__table__  # type: ignore[attr-defined]
    insert_statement = pg_insert(player_table).values(
        [
            {
                "steamid64": int(steamid64),
                "name": steamid64,
                "created_at": now,
                "updated_at": now,
            }
            for steamid64 in normalized_steamid64s
        ]
    )
    await session.exec(
        insert_statement.on_conflict_do_nothing(
            index_elements=[player_table.c.steamid64],
        )
    )


def parse_kz_map_info_authors(row: dict[str, Any]) -> ParsedKzMapInfoAuthors | None:
    raw_name = row.get("name")
    if not isinstance(raw_name, str) or not raw_name.strip():
        return None

    raw_id = row.get("id")
    map_id: int | None = None
    if isinstance(raw_id, str) and raw_id.strip().isdigit():
        map_id = int(raw_id.strip())
    elif isinstance(raw_id, int):
        map_id = raw_id

    mapper_names = _split_author_text(row.get("mapper_name"))
    mapper_steamids = _split_author_text(row.get("mapper_steamid64"))
    steamid_authors: list[str] = []
    no_steamid_names: list[str] = []

    for index, mapper_name in enumerate(mapper_names):
        mapper_steamid = mapper_steamids[index] if index < len(mapper_steamids) else ""
        if STEAMID64_PATTERN.fullmatch(mapper_steamid):
            steamid_authors.append(mapper_steamid)
        else:
            no_steamid_names.append(mapper_name)

    if len(mapper_steamids) > len(mapper_names):
        steamid_authors.extend(mapper_steamids[len(mapper_names) :])

    return ParsedKzMapInfoAuthors(
        map_id=map_id,
        map_name=raw_name.strip(),
        authors=normalize_steamid64_list(steamid_authors),
        no_steamid_names=normalize_name_list(no_steamid_names),
    )


async def fetch_kz_map_info_rows(
    *,
    client: httpx.AsyncClient | None = None,
    url: str = KZ_MAP_INFO_GLOBAL_URL,
) -> list[dict[str, Any]]:
    resolved_client = client or httpx.AsyncClient(timeout=30.0)
    should_close = client is None
    try:
        response = await resolved_client.get(url)
        response.raise_for_status()
        payload = response.json()
    finally:
        if should_close:
            await resolved_client.aclose()

    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


async def seed_map_authors_from_kz_map_info(
    *,
    session: AsyncSession,
    rows: list[dict[str, Any]] | None = None,
) -> MapAuthorSeedResult:
    source_rows = rows if rows is not None else await fetch_kz_map_info_rows()
    parsed_rows = [
        parsed
        for row in source_rows
        if (parsed := parse_kz_map_info_authors(row)) is not None
    ]
    if not parsed_rows:
        return MapAuthorSeedResult(processed=len(source_rows), matched=0, updated=0, skipped=0)

    map_ids = [row.map_id for row in parsed_rows if row.map_id is not None]
    map_names = [row.map_name for row in parsed_rows]
    maps = list(
        (
            await session.exec(
                select(Map).where(or_(col(Map.id).in_(map_ids), col(Map.name).in_(map_names)))
            )
        ).all()
    )
    maps_by_id = {map_obj.id: map_obj for map_obj in maps}
    maps_by_name = {map_obj.name: map_obj for map_obj in maps}

    matched = 0
    updated = 0
    skipped = 0
    all_author_steamid64s: list[str] = []
    for parsed in parsed_rows:
        map_obj = (
            maps_by_id.get(parsed.map_id)
            if parsed.map_id is not None
            else None
        ) or maps_by_name.get(parsed.map_name)
        if map_obj is None:
            skipped += 1
            continue
        matched += 1
        merged_authors, merged_names = merge_author_fields(
            existing_authors=map_obj.authors,
            existing_no_steamid_names=map_obj.no_steamid_names,
            incoming_authors=parsed.authors,
            incoming_no_steamid_names=parsed.no_steamid_names,
        )
        all_author_steamid64s.extend(merged_authors)
        if merged_authors == (map_obj.authors or []) and merged_names == (
            map_obj.no_steamid_names or []
        ):
            continue
        map_obj.authors = merged_authors
        map_obj.no_steamid_names = merged_names
        session.add(map_obj)
        updated += 1

    await ensure_author_players_exist(
        session=session,
        author_steamid64s=all_author_steamid64s,
    )
    await session.commit()
    return MapAuthorSeedResult(
        processed=len(source_rows),
        matched=matched,
        updated=updated,
        skipped=skipped,
    )
