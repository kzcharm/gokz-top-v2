"""Manually import map skill aggregates and ordered segments from an index.json file."""

import argparse
import asyncio
import json
import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import async_session_maker
from app.models import Map, MapSkill

SKILL_NAMES = ("boxtech", "strafe", "bhop", "climb", "ladder", "slide")
ALL_SKILLS = set(SKILL_NAMES) | {"unknown"}
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SkillEntry:
    map_name: str
    skills: dict[str, Decimal]
    segments: list[dict[str, str | int]]


@dataclass(frozen=True)
class ImportResult:
    entries: int
    imported_rows: int
    unmatched_names: list[str]


def parse_index(path: Path) -> list[SkillEntry]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read map skill index {path}: {exc}") from exc

    if not isinstance(payload, dict) or payload.get("format_version") != 3:
        raise ValueError("Expected a map skill index with format_version 3")
    maps = payload.get("maps")
    if not isinstance(maps, list):
        raise ValueError("Expected maps to be an array")

    entries: list[SkillEntry] = []
    seen: set[str] = set()
    for index, item in enumerate(maps):
        if not isinstance(item, dict):
            raise ValueError(f"maps[{index}] must be an object")
        name = item.get("map_name")
        if not isinstance(name, str) or not name or len(name) > 255:
            raise ValueError(f"maps[{index}].map_name must be a nonempty map name")
        if name in seen:
            raise ValueError(f"Duplicate map_name in input: {name}")
        seen.add(name)

        raw_skills = item.get("skills")
        if not isinstance(raw_skills, dict) or raw_skills.keys() != ALL_SKILLS:
            raise ValueError(
                f"{name}: skills must contain exactly the six skills and unknown"
            )
        skills: dict[str, Decimal] = {}
        for skill in ALL_SKILLS:
            raw = raw_skills[skill]
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                raise ValueError(f"{name}: {skill} must be a number")
            try:
                value = Decimal(str(raw))
            except InvalidOperation as exc:
                raise ValueError(f"{name}: invalid {skill} fraction") from exc
            exponent = value.as_tuple().exponent
            if (
                not value.is_finite()
                or not 0 <= value <= 1
                or not isinstance(exponent, int)
                or exponent < -4
            ):
                raise ValueError(
                    f"{name}: {skill} must be between 0 and 1 with at most four decimals"
                )
            skills[skill] = value

        raw_segments = item.get("segments")
        if not isinstance(raw_segments, list):
            raise ValueError(f"{name}: segments must be an array")
        segments: list[dict[str, str | int]] = []
        for segment_index, segment in enumerate(raw_segments):
            if (
                not isinstance(segment, dict)
                or segment.keys() != {"skill", "tick_count"}
                or not isinstance(segment.get("skill"), str)
                or segment.get("skill") not in ALL_SKILLS
                or type(segment.get("tick_count")) is not int
                or segment["tick_count"] <= 0
            ):
                raise ValueError(f"{name}: invalid segments[{segment_index}]")
            segments.append(
                {"skill": segment["skill"], "tick_count": segment["tick_count"]}
            )
        entries.append(SkillEntry(map_name=name, skills=skills, segments=segments))
    return entries


async def import_map_skills(
    *, session: AsyncSession, entries: list[SkillEntry]
) -> ImportResult:
    names = [entry.map_name for entry in entries]
    rows = (
        await session.exec(select(Map.id, Map.name).where(col(Map.name).in_(names)))
        if names
        else None
    )
    ids_by_name: dict[str, list[int]] = {}
    if rows is not None:
        for map_id, map_name in rows.all():
            ids_by_name.setdefault(map_name, []).append(map_id)

    unmatched: list[str] = []
    values: list[dict[str, Any]] = []
    for entry in entries:
        map_ids = ids_by_name.get(entry.map_name)
        if not map_ids:
            unmatched.append(entry.map_name)
            continue
        for map_id in map_ids:
            values.append(
                {
                    "map_id": map_id,
                    **{key: entry.skills[key] for key in SKILL_NAMES},
                    "segments": entry.segments,
                }
            )

    for start in range(0, len(values), 100):
        statement = insert(MapSkill).values(values[start : start + 100])
        await session.exec(
            statement.on_conflict_do_update(
                index_elements=["map_id"],
                set_={
                    key: getattr(statement.excluded, key)
                    for key in (*SKILL_NAMES, "segments")
                },
            )
        )
    await session.commit()
    return ImportResult(
        entries=len(entries), imported_rows=len(values), unmatched_names=unmatched
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import map skill analysis from index.json"
    )
    parser.add_argument("index", type=Path, help="Path to the source index.json")
    args = parser.parse_args()
    try:
        entries = parse_index(args.index)
    except ValueError as exc:
        parser.error(str(exc))

    async def run() -> ImportResult:
        async with async_session_maker() as session:
            return await import_map_skills(session=session, entries=entries)

    result = asyncio.run(run())
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logger.info(
        "Parsed %s maps; upserted %s rows; unmatched %s",
        result.entries,
        result.imported_rows,
        len(result.unmatched_names),
    )
    for name in result.unmatched_names:
        logger.info("Unmatched: %s", name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
