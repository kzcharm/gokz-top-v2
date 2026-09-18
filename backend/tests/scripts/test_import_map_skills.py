import json
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.importers.map_skills import import_map_skills, parse_index
from app.models import Map, MapSkill


def _entry(name: str, *, tick_count: int = 42) -> dict[str, object]:
    return {
        "map_name": name,
        "skills": {
            "boxtech": 0.1,
            "strafe": 0.2,
            "bhop": 0.3,
            "climb": 0.1,
            "ladder": 0.1,
            "slide": 0.1,
            "unknown": 0.1,
        },
        "segments": [
            {"skill": "bhop", "tick_count": tick_count},
            {"skill": "unknown", "tick_count": 1},
        ],
    }


def _index(path: Path, maps: list[dict[str, object]]) -> Path:
    path.write_text(json.dumps({"format_version": 3, "maps": maps}), encoding="utf-8")
    return path


def test_parse_index_preserves_order_and_validates_all_entries(tmp_path: Path) -> None:
    path = _index(tmp_path / "index.json", [_entry("kz_alpha")])
    entries = parse_index(path)
    assert entries[0].skills["bhop"] == Decimal("0.3")
    assert entries[0].segments == [
        {"skill": "bhop", "tick_count": 42},
        {"skill": "unknown", "tick_count": 1},
    ]

    for invalid in (0, -2, True, 1.5):
        bad = _entry("kz_alpha")
        bad["segments"] = [{"skill": "bhop", "tick_count": invalid}]
        with pytest.raises(ValueError, match="invalid segments"):
            parse_index(_index(path, [bad]))

    bad = _entry("kz_alpha")
    bad["skills"] = {**bad["skills"], "bhop": 1.1}  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="bhop must be between"):
        parse_index(_index(path, [bad]))
    with pytest.raises(ValueError, match="Duplicate map_name"):
        parse_index(_index(path, [_entry("kz_alpha"), _entry("kz_alpha")]))


@pytest.mark.asyncio
async def test_import_map_skills_upserts_segments_and_retains_omitted_rows(
    db: AsyncSession, tmp_path: Path
) -> None:
    maps = [
        Map(id=990101 + index, name=name, filesize=0)
        for index, name in enumerate(("kz_duplicate", "kz_duplicate", "kz_untouched"))
    ]
    db.add_all(maps)
    await db.commit()

    entries = parse_index(
        _index(
            tmp_path / "index.json", [_entry("kz_duplicate"), _entry("kz_untouched")]
        )
    )
    result = await import_map_skills(session=db, entries=entries)
    assert result.imported_rows == 3
    assert not result.unmatched_names

    update = parse_index(
        _index(
            tmp_path / "index.json",
            [_entry("kz_duplicate", tick_count=99), _entry("not_in_db")],
        )
    )
    result = await import_map_skills(session=db, entries=update)
    assert result.imported_rows == 2
    assert result.unmatched_names == ["not_in_db"]
    rows = (
        await db.exec(
            select(MapSkill).where(col(MapSkill.map_id).in_([m.id for m in maps]))
        )
    ).all()
    assert len(rows) == 3
    for row in rows:
        assert row.bhop == Decimal("0.3000")
        assert row.segments[0]["tick_count"] == (42 if row.map_id == maps[2].id else 99)
    assert (
        await db.exec(
            select(func.count())
            .select_from(MapSkill)
            .where(col(MapSkill.map_id).in_([m.id for m in maps]))
        )
    ).one() == 3
