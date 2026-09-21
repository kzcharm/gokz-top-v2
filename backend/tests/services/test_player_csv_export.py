import csv
import gzip
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import (
    Ban,
    BanType,
    KZMode,
    Map,
    Player,
    PlayerSession,
    Record,
    ServerGlobalapi,
    ServerGroup,
    generate_uuid7,
)
from app.services import player_csv_export, record_csv_export


@pytest.mark.asyncio
async def test_player_csv_export_uses_global_sessions_and_permanent_bans(
    db: AsyncSession,
    tmp_path: Path,
) -> None:
    selected_group = ServerGroup(
        name="Player Export Selected",
        custom_id="player-export-selected",
        api_key=str(uuid.uuid4()),
    )
    other_group = ServerGroup(
        name="Player Export Other",
        custom_id="player-export-other",
        api_key=str(uuid.uuid4()),
    )
    db.add_all([selected_group, other_group])
    await db.flush()

    server_id = 979_051
    db.add(
        ServerGlobalapi(
            id=server_id,
            name="Player Export Server",
            group_id=selected_group.id,
        )
    )
    first_steamid64 = record_csv_export.STEAMID64_ACCOUNT_ID_BASE + 2_000_001
    second_steamid64 = record_csv_export.STEAMID64_ACCOUNT_ID_BASE + 2_000_002
    db.add_all(
        [
            Player(
                steamid64=first_steamid64,
                name="Original Player",
                alias="Preferred Alias",
                country="DE",
            ),
            Player(
                steamid64=second_steamid64,
                name="Fallback Name",
                alias=None,
                country=None,
            ),
        ]
    )
    map_row = Map(id=979_052, name="kz_player_export")
    db.add(map_row)
    await db.flush()

    first_record_at = datetime(2026, 1, 2, 12, tzinfo=UTC)
    last_record_at = datetime(2026, 1, 4, 12, tzinfo=UTC)
    db.add_all(
        [
            Record(
                id=9_790_510,
                steamid64=first_steamid64,
                server_id=server_id,
                mode=KZMode.KZT,
                map_id=map_row.id,
                time=Decimal("40.000"),
                created_at=first_record_at,
                updated_at=first_record_at,
            ),
            Record(
                id=9_790_511,
                steamid64=first_steamid64,
                server_id=server_id,
                mode=KZMode.NKZ,
                map_id=map_row.id,
                time=Decimal("39.000"),
                created_at=last_record_at,
                updated_at=last_record_at,
            ),
            Record(
                id=9_790_512,
                steamid64=second_steamid64,
                server_id=server_id,
                mode=KZMode.VNL,
                map_id=map_row.id,
                time=Decimal("50.000"),
                created_at=last_record_at,
                updated_at=last_record_at,
            ),
        ]
    )

    earliest_session_at = datetime(2026, 1, 1, 10, tzinfo=UTC)
    latest_session_at = datetime(2026, 1, 5, 10, tzinfo=UTC)
    latest_disconnect_at = datetime(2026, 1, 6, 10, tzinfo=UTC)
    db.add_all(
        [
            PlayerSession(
                id=generate_uuid7(timestamp=earliest_session_at),
                player_steamid64=first_steamid64,
                server_group_id=selected_group.id,
                connected_at=earliest_session_at,
                disconnect_at=earliest_session_at,
                last_heartbeat_at=earliest_session_at,
                ip_address="198.51.100.10",
                map_name=map_row.name,
            ),
            PlayerSession(
                id=generate_uuid7(timestamp=latest_session_at),
                player_steamid64=first_steamid64,
                server_group_id=other_group.id,
                connected_at=latest_session_at,
                disconnect_at=latest_disconnect_at,
                last_heartbeat_at=latest_disconnect_at,
                ip_address="203.0.113.20",
                map_name="kz_other_server",
            ),
        ]
    )
    db.add_all(
        [
            Ban(
                steamid64=first_steamid64,
                ban_type=BanType.OTHER,
                expires_at=None,
            ),
            Ban(
                steamid64=second_steamid64,
                ban_type=BanType.OTHER,
                expires_at=datetime(2027, 1, 1, tzinfo=UTC),
            ),
        ]
    )
    await db.flush()

    output_path = tmp_path / "players.csv.gz"
    exported_players = await player_csv_export._write_csv(
        session=db,
        output_path=output_path,
        server_ids=(server_id,),
        after=None,
        before=None,
        force=False,
    )

    assert exported_players == 2
    with gzip.open(output_path, "rt", encoding="utf-8", newline="") as export_file:
        rows = list(csv.DictReader(export_file))
    assert tuple(rows[0]) == player_csv_export.CSV_HEADER
    assert rows[0] == {
        "steamid32": "2000001",
        "steamid64": str(first_steamid64),
        "alias": "Preferred Alias",
        "cheater": "1",
        "ip": "203.0.113.20",
        "last_played_at": "2026-01-06T10:00:00.000Z",
        "country": "DE",
        "created_at": "2026-01-01T10:00:00.000Z",
    }
    assert rows[1]["alias"] == "Fallback Name"
    assert rows[1]["cheater"] == "0"
    assert rows[1]["ip"] == ""
    assert rows[1]["last_played_at"] == "2026-01-04T12:00:00.000Z"
    assert rows[1]["created_at"] == "2026-01-04T12:00:00.000Z"
