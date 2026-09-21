import csv
import gzip
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import KZMode, Map, Player, Record, ServerGlobalapi, ServerGroup
from app.services import record_csv_export


async def _seed_export_rows(db: AsyncSession) -> tuple[ServerGroup, int]:
    group = ServerGroup(
        name="AXE CSV Export Test",
        custom_id="axe-csv-export-test",
        api_key=str(uuid.uuid4()),
    )
    db.add(group)
    await db.flush()

    server_id = 979_041
    db.add(ServerGlobalapi(id=server_id, name="AXE Test", group_id=group.id))
    valid_steamid64 = record_csv_export.STEAMID64_ACCOUNT_ID_BASE + 1_234_567
    bad_steamid64 = record_csv_export.STEAMID64_ACCOUNT_ID_BASE - 1
    db.add_all(
        [
            Player(
                steamid64=valid_steamid64,
                name="Original Name",
                alias='Alias, "Quoted"',
                country="DE",
            ),
            Player(steamid64=bad_steamid64, name="Bad SteamID"),
        ]
    )
    map_row = Map(
        id=979_042,
        name="kz_a_map_name_that_is_far_longer_than_thirty_two_characters",
    )
    db.add(map_row)
    await db.flush()

    created_at = datetime(2026, 9, 1, 12, 34, 56, tzinfo=UTC)
    for offset, mode in enumerate((KZMode.VNL, KZMode.SKZ, KZMode.KZT, KZMode.NKZ)):
        db.add(
            Record(
                id=9_790_410 + offset,
                steamid64=valid_steamid64,
                server_id=server_id,
                mode=mode,
                map_id=map_row.id,
                stage=offset,
                time=Decimal("42.853"),
                teleports=offset,
                created_at=created_at,
                updated_at=created_at,
                replay_id=None if offset == 0 else 4_000 + offset,
            )
        )
    db.add(
        Record(
            id=9_790_420,
            steamid64=valid_steamid64,
            server_id=server_id,
            mode=KZMode.KZT,
            map_id=map_row.id,
            time=Decimal("50.000"),
            created_at=created_at,
            updated_at=created_at,
            is_valid=False,
        )
    )
    db.add(
        Record(
            id=9_790_421,
            steamid64=bad_steamid64,
            server_id=server_id,
            mode=KZMode.NKZ,
            map_id=map_row.id,
            time=Decimal("51.000"),
            created_at=created_at,
            updated_at=created_at,
        )
    )
    await db.flush()
    return group, server_id


@pytest.mark.asyncio
async def test_record_csv_export_contains_expected_rows_and_fields(
    db: AsyncSession,
    tmp_path: Path,
) -> None:
    _, server_id = await _seed_export_rows(db)
    predicates = record_csv_export._selection_predicates(
        server_ids=(server_id,),
        after=None,
        before=None,
    )
    invalid_rows, bad_steamid_rows = await record_csv_export._get_exclusion_counts(
        session=db,
        selection_predicates=predicates,
    )
    output_path = tmp_path / "records.csv.gz"

    exported_rows = await record_csv_export._write_csv(
        session=db,
        output_path=output_path,
        selection_predicates=predicates,
        force=False,
    )

    assert exported_rows == 4
    assert invalid_rows == 1
    assert bad_steamid_rows == 1
    with gzip.open(output_path, "rt", encoding="utf-8", newline="") as export_file:
        rows = list(csv.DictReader(export_file))
    assert tuple(rows[0]) == record_csv_export.CSV_HEADER
    assert [row["mode"] for row in rows] == ["VNL", "SKZ", "KZT", "NKZ"]
    assert [row["local_mode"] for row in rows] == ["0", "1", "2", "3"]
    assert rows[0]["player_name"] == 'Alias, "Quoted"'
    assert rows[0]["player_country"] == "DE"
    assert len(rows[0]["map_name"]) > 32
    assert rows[0]["runtime_seconds"] == "42.853"
    assert rows[0]["runtime_ms"] == "42853"
    assert rows[0]["replay_id"] == ""
    assert rows[0]["is_valid"] == "true"


@pytest.mark.asyncio
async def test_record_csv_export_resolves_group_identifiers_and_rejects_overwrite(
    db: AsyncSession,
    tmp_path: Path,
) -> None:
    group, server_id = await _seed_export_rows(db)

    for identifier in (str(group.id), group.custom_id, group.name):
        assert await record_csv_export._resolve_server_ids(
            session=db,
            server_ids=None,
            server_groups=[identifier],
        ) == (server_id,)

    output_path = tmp_path / "records.csv.gz"
    output_path.write_bytes(b"existing")
    with pytest.raises(ValueError, match="already exists"):
        await record_csv_export._write_csv(
            session=db,
            output_path=output_path,
            selection_predicates=record_csv_export._selection_predicates(
                server_ids=(server_id,),
                after=None,
                before=None,
            ),
            force=False,
        )
    assert output_path.read_bytes() == b"existing"


def test_record_csv_export_datetime_boundaries_are_inclusive_utc() -> None:
    assert record_csv_export.parse_datetime_boundary("2026-09-01") == datetime(
        2026, 9, 1, tzinfo=UTC
    )
    assert record_csv_export.parse_datetime_boundary(
        "2026-09-01", is_end=True
    ) == datetime(2026, 9, 1, 23, 59, 59, 999999, tzinfo=UTC)
    assert record_csv_export.parse_datetime_boundary(
        "2026-09-01T14:00:00+02:00"
    ) == datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_record_csv_export_requires_exactly_one_selector(
    db: AsyncSession,
) -> None:
    with pytest.raises(ValueError, match="exactly one selector"):
        await record_csv_export._resolve_server_ids(
            session=db,
            server_ids=None,
            server_groups=None,
        )
    with pytest.raises(ValueError, match="exactly one selector"):
        await record_csv_export._resolve_server_ids(
            session=db,
            server_ids=[1683],
            server_groups=["axe"],
        )
