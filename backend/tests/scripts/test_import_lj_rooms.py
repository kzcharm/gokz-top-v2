import json
from pathlib import Path

import pytest
from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.importers.lj_rooms import import_lj_rooms, parse_export
from app.models import Map, MapLJRoom


def _map_entry(
    map_id: int, name: str, *, distance: int = 260, rooms: bool = True
) -> dict[str, object]:
    return {
        "map_name": name,
        "api_map_id": map_id,
        "filesize": 123456,
        "rooms": (
            [
                {
                    "rank": 0,
                    "score": 42.5,
                    "spots": [
                        {
                            "distance": distance,
                            "raw_distance": float(distance),
                            "origin": [1.0, 2.0, 3.0],
                            "angles": [0.0, 90.0],
                            "landing": [4.0, 5.0, 6.0],
                        }
                    ],
                }
            ]
            if rooms
            else []
        ),
    }


def _export(path: Path, maps: list[dict[str, object]]) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "detector_version": 8,
                "generated_at": "2026-09-22T09:48:36Z",
                "maps": maps,
            }
        ),
        encoding="utf-8",
    )
    return path


def test_parse_export_validates_shape_and_duplicates(tmp_path: Path) -> None:
    path = _export(tmp_path / "rooms.json", [_map_entry(990201, "kz_alpha")])
    entries = parse_export(path)
    assert entries[0].map_id == 990201
    assert entries[0].data["rooms"][0]["spots"][0]["distance"] == 260

    duplicate_id = [_map_entry(990201, "kz_alpha"), _map_entry(990201, "kz_beta")]
    with pytest.raises(ValueError, match="Duplicate api_map_id"):
        parse_export(_export(path, duplicate_id))

    duplicate_name = [
        _map_entry(990201, "kz_alpha"),
        _map_entry(990202, "kz_alpha"),
    ]
    with pytest.raises(ValueError, match="Duplicate map_name"):
        parse_export(_export(path, duplicate_name))

    invalid = _map_entry(990201, "kz_alpha")
    invalid["rooms"][0]["spots"][0]["origin"] = [1.0, 2.0]  # type: ignore[index]
    with pytest.raises(ValueError, match="origin must contain exactly 3"):
        parse_export(_export(path, [invalid]))

    duplicate_rank = _map_entry(990201, "kz_alpha")
    duplicate_rank["rooms"].append(duplicate_rank["rooms"][0])  # type: ignore[union-attr]
    with pytest.raises(ValueError, match="duplicate room rank 0"):
        parse_export(_export(path, [duplicate_rank]))


@pytest.mark.asyncio
async def test_import_lj_rooms_upserts_matches_and_retains_omitted_rows(
    db: AsyncSession, tmp_path: Path
) -> None:
    maps = [
        Map(id=990211, name="kz_lj_one", filesize=0),
        Map(id=990212, name="kz_lj_two", filesize=0),
        Map(id=990213, name="kz_database_name", filesize=0),
    ]
    await db.exec(delete(MapLJRoom).where(MapLJRoom.id.in_([m.id for m in maps])))
    await db.exec(delete(Map).where(Map.id.in_([m.id for m in maps])))
    db.add_all(maps)
    await db.commit()

    entries = parse_export(
        _export(
            tmp_path / "rooms.json",
            [
                _map_entry(990211, "kz_lj_one"),
                _map_entry(990212, "kz_lj_two", rooms=False),
                _map_entry(990213, "kz_export_name"),
                _map_entry(990299, "kz_missing"),
            ],
        )
    )
    result = await import_lj_rooms(session=db, entries=entries)
    assert result.entries == 4
    assert result.imported_rows == 2
    assert result.unmatched_ids == [990299]
    assert result.name_mismatches == [
        "990213: export=kz_export_name database=kz_database_name"
    ]

    rows = (
        await db.exec(select(MapLJRoom).where(MapLJRoom.id.in_([990211, 990212])))
    ).all()
    assert len(rows) == 2
    assert next(row for row in rows if row.id == 990212).data["rooms"] == []

    update = parse_export(
        _export(
            tmp_path / "rooms.json",
            [_map_entry(990211, "kz_lj_one", distance=275)],
        )
    )
    await import_lj_rooms(session=db, entries=update)
    updated_row = await db.get(MapLJRoom, 990211)
    assert updated_row is not None
    await db.refresh(updated_row)
    assert updated_row.data["rooms"][0]["spots"][0]["distance"] == 275
    assert await db.get(MapLJRoom, 990212) is not None
