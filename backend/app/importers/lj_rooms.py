"""Manually import detected long-jump rooms from an analyzer JSON export."""

import argparse
import asyncio
import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeGuard

from pydantic import ValidationError
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import async_session_maker
from app.models import Map, MapLJRoom, MapLJRoomPayload

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LJRoomEntry:
    map_id: int
    map_name: str
    data: dict[str, Any]


@dataclass(frozen=True)
class ImportResult:
    entries: int
    imported_rows: int
    unmatched_ids: list[int]
    name_mismatches: list[str]


def _is_int(value: object) -> TypeGuard[int]:
    return type(value) is int


def _is_number(value: object) -> TypeGuard[int | float]:
    return not isinstance(value, bool) and isinstance(value, (int, float))


def _validate_vector(value: object, *, length: int, path: str) -> None:
    if (
        not isinstance(value, list)
        or len(value) != length
        or any(not _is_number(component) for component in value)
        or any(not math.isfinite(float(component)) for component in value)
    ):
        raise ValueError(f"{path} must contain exactly {length} finite numbers")


def _validate_map_item(item: object, *, index: int) -> MapLJRoomPayload:
    if not isinstance(item, dict):
        raise ValueError(f"maps[{index}] must be an object")
    if item.keys() != {"map_name", "api_map_id", "filesize", "rooms"}:
        raise ValueError(
            f"maps[{index}] must contain map_name, api_map_id, filesize, and rooms"
        )

    map_name = item.get("map_name")
    map_id = item.get("api_map_id")
    filesize = item.get("filesize")
    rooms = item.get("rooms")
    if not isinstance(map_name, str) or not map_name or len(map_name) > 255:
        raise ValueError(f"maps[{index}].map_name must be a nonempty map name")
    if not _is_int(map_id) or map_id <= 0:
        raise ValueError(f"{map_name}: api_map_id must be a positive integer")
    if not _is_int(filesize) or filesize < 0:
        raise ValueError(f"{map_name}: filesize must be a nonnegative integer")
    if not isinstance(rooms, list):
        raise ValueError(f"{map_name}: rooms must be an array")

    seen_room_ranks: set[int] = set()
    for room_index, room in enumerate(rooms):
        room_path = f"{map_name}.rooms[{room_index}]"
        if not isinstance(room, dict) or room.keys() != {"rank", "score", "spots"}:
            raise ValueError(f"{room_path} must contain rank, score, and spots")
        rank = room.get("rank")
        score = room.get("score")
        spots = room.get("spots")
        if not _is_int(rank) or rank < 0:
            raise ValueError(f"{room_path}.rank must be a nonnegative integer")
        if rank in seen_room_ranks:
            raise ValueError(f"{map_name}: duplicate room rank {rank}")
        seen_room_ranks.add(rank)
        if not _is_number(score) or not math.isfinite(float(score)) or score < 0:
            raise ValueError(f"{room_path}.score must be a nonnegative finite number")
        if not isinstance(spots, list):
            raise ValueError(f"{room_path}.spots must be an array")

        for spot_index, spot in enumerate(spots):
            spot_path = f"{room_path}.spots[{spot_index}]"
            if not isinstance(spot, dict) or spot.keys() != {
                "distance",
                "raw_distance",
                "origin",
                "angles",
                "landing",
            }:
                raise ValueError(
                    f"{spot_path} must contain distance, raw_distance, origin, angles, and landing"
                )
            distance = spot.get("distance")
            raw_distance = spot.get("raw_distance")
            if not _is_int(distance) or distance <= 0:
                raise ValueError(f"{spot_path}.distance must be a positive integer")
            if (
                not _is_number(raw_distance)
                or not math.isfinite(float(raw_distance))
                or raw_distance <= 0
            ):
                raise ValueError(
                    f"{spot_path}.raw_distance must be a positive finite number"
                )
            _validate_vector(spot.get("origin"), length=3, path=f"{spot_path}.origin")
            _validate_vector(spot.get("angles"), length=2, path=f"{spot_path}.angles")
            _validate_vector(spot.get("landing"), length=3, path=f"{spot_path}.landing")

    try:
        return MapLJRoomPayload.model_validate(item)
    except ValidationError as exc:
        raise ValueError(f"{map_name}: invalid LJ-room payload: {exc}") from exc


def parse_export(path: Path) -> list[LJRoomEntry]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read LJ-room export {path}: {exc}") from exc

    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("Expected an LJ-room export with schema_version 1")
    if not _is_int(payload.get("detector_version")):
        raise ValueError("Expected detector_version to be an integer")
    if not isinstance(payload.get("generated_at"), str):
        raise ValueError("Expected generated_at to be a string")
    maps = payload.get("maps")
    if not isinstance(maps, list):
        raise ValueError("Expected maps to be an array")

    entries: list[LJRoomEntry] = []
    seen_ids: set[int] = set()
    seen_names: set[str] = set()
    for index, item in enumerate(maps):
        parsed = _validate_map_item(item, index=index)
        if parsed.api_map_id in seen_ids:
            raise ValueError(f"Duplicate api_map_id in input: {parsed.api_map_id}")
        if parsed.map_name in seen_names:
            raise ValueError(f"Duplicate map_name in input: {parsed.map_name}")
        seen_ids.add(parsed.api_map_id)
        seen_names.add(parsed.map_name)
        entries.append(
            LJRoomEntry(
                map_id=parsed.api_map_id,
                map_name=parsed.map_name,
                data=parsed.model_dump(mode="json"),
            )
        )
    return entries


async def import_lj_rooms(
    *, session: AsyncSession, entries: list[LJRoomEntry]
) -> ImportResult:
    map_ids = [entry.map_id for entry in entries]
    rows = (
        await session.exec(select(Map.id, Map.name).where(col(Map.id).in_(map_ids)))
        if map_ids
        else None
    )
    names_by_id = dict(rows.all()) if rows is not None else {}

    unmatched_ids: list[int] = []
    name_mismatches: list[str] = []
    values: list[dict[str, Any]] = []
    for entry in entries:
        database_name = names_by_id.get(entry.map_id)
        if database_name is None:
            unmatched_ids.append(entry.map_id)
            continue
        if database_name != entry.map_name:
            name_mismatches.append(
                f"{entry.map_id}: export={entry.map_name} database={database_name}"
            )
            continue
        values.append({"id": entry.map_id, "data": entry.data})

    for start in range(0, len(values), 100):
        statement = insert(MapLJRoom).values(values[start : start + 100])
        await session.exec(
            statement.on_conflict_do_update(
                index_elements=["id"], set_={"data": statement.excluded.data}
            )
        )
    await session.commit()
    return ImportResult(
        entries=len(entries),
        imported_rows=len(values),
        unmatched_ids=unmatched_ids,
        name_mismatches=name_mismatches,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import detected long-jump rooms from an analyzer JSON export"
    )
    parser.add_argument("export", type=Path, help="Path to gokz-lj-rooms.json")
    args = parser.parse_args()
    try:
        entries = parse_export(args.export)
    except ValueError as exc:
        parser.error(str(exc))

    async def run() -> ImportResult:
        async with async_session_maker() as session:
            return await import_lj_rooms(session=session, entries=entries)

    result = asyncio.run(run())
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logger.info(
        "Parsed %s maps; upserted %s rows; unmatched IDs %s; name mismatches %s",
        result.entries,
        result.imported_rows,
        len(result.unmatched_ids),
        len(result.name_mismatches),
    )
    for map_id in result.unmatched_ids:
        logger.info("Unmatched map ID: %s", map_id)
    for mismatch in result.name_mismatches:
        logger.info("Map name mismatch: %s", mismatch)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
