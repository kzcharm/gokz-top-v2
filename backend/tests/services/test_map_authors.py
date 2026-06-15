from datetime import UTC, datetime

import pytest
from sqlmodel import delete
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Map, Player
from app.services.map_authors import (
    merge_author_fields,
    normalize_author_fields,
    parse_kz_map_info_authors,
    seed_map_authors_from_kz_map_info,
)


def test_parse_kz_map_info_authors_splits_paired_mapper_fields() -> None:
    parsed = parse_kz_map_info_authors(
        {
            "id": "269",
            "name": "bkz_cakewalk",
            "mapper_name": "zPrince, GameChaos",
            "mapper_steamid64": "76561198047032125, 76561198165203332",
        }
    )

    assert parsed is not None
    assert parsed.map_id == 269
    assert parsed.map_name == "bkz_cakewalk"
    assert parsed.authors == ["76561198047032125", "76561198165203332"]
    assert parsed.no_steamid_names == []


def test_parse_kz_map_info_authors_keeps_names_without_steamids() -> None:
    parsed = parse_kz_map_info_authors(
        {
            "id": "212",
            "name": "bkz_hellokitty_v2",
            "mapper_name": "Kore, Known Mapper",
            "mapper_steamid64": "{}, 76561198000000001",
        }
    )

    assert parsed is not None
    assert parsed.authors == ["76561198000000001"]
    assert parsed.no_steamid_names == ["Kore"]


def test_parse_kz_map_info_authors_ignores_object_values() -> None:
    parsed = parse_kz_map_info_authors(
        {
            "id": "1269",
            "name": "kz_colorado",
            "mapper_name": {},
            "mapper_steamid64": {},
        }
    )

    assert parsed is not None
    assert parsed.authors == []
    assert parsed.no_steamid_names == []


def test_author_field_normalization_separates_steamids_from_names() -> None:
    authors, no_steamid_names = normalize_author_fields(
        authors=[" 76561198000000001 ", "Mapper Name", "76561198000000001"],
        no_steamid_names=["Other Mapper", "76561198000000002"],
    )

    assert authors == ["76561198000000001"]
    assert no_steamid_names == ["Other Mapper", "Mapper Name"]


def test_author_field_merge_preserves_existing_and_appends_new_values() -> None:
    authors, no_steamid_names = merge_author_fields(
        existing_authors=["76561198000000001"],
        existing_no_steamid_names=["Name Only"],
        incoming_authors=["76561198000000001", "76561198000000002"],
        incoming_no_steamid_names=["Name Only", "Second Name"],
    )

    assert authors == ["76561198000000001", "76561198000000002"]
    assert no_steamid_names == ["Name Only", "Second Name"]


@pytest.mark.asyncio
async def test_seed_map_authors_from_kz_map_info_matches_by_id_and_name(
    db: AsyncSession,
) -> None:
    await db.exec(delete(Map).where(Map.id.in_([994001, 994002])))
    await db.commit()
    db.add(
        Map(
            id=994001,
            name="kz_seed_by_id",
            filesize=1,
            validated=True,
            difficulty=1,
            created_on=datetime(2021, 1, 1, tzinfo=UTC),
            updated_on=datetime(2021, 1, 1, tzinfo=UTC),
            approved_by_steamid64=0,
            authors=["76561198000000009"],
        )
    )
    db.add(
        Map(
            id=994002,
            name="kz_seed_by_name",
            filesize=1,
            validated=True,
            difficulty=1,
            created_on=datetime(2021, 1, 1, tzinfo=UTC),
            updated_on=datetime(2021, 1, 1, tzinfo=UTC),
            approved_by_steamid64=0,
        )
    )
    await db.commit()

    result = await seed_map_authors_from_kz_map_info(
        session=db,
        rows=[
            {
                "id": "994001",
                "name": "wrong_name",
                "mapper_name": "Known",
                "mapper_steamid64": "76561198000000001",
            },
            {
                "id": "0",
                "name": "kz_seed_by_name",
                "mapper_name": "Name Only",
            },
        ],
    )

    by_id = await db.get(Map, 994001)
    by_name = await db.get(Map, 994002)
    assert result.processed == 2
    assert result.matched == 2
    assert result.updated == 2
    assert by_id is not None
    assert by_id.authors == ["76561198000000009", "76561198000000001"]
    assert by_name is not None
    assert by_name.no_steamid_names == ["Name Only"]

    existing_author_player = await db.get(Player, 76561198000000009)
    seeded_author_player = await db.get(Player, 76561198000000001)
    assert existing_author_player is not None
    assert existing_author_player.name == "76561198000000009"
    assert seeded_author_player is not None
    assert seeded_author_player.name == "76561198000000001"
