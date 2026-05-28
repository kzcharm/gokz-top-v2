from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.importers.v1_player_profile_fields import (
    import_v1_player_profile_fields,
    iter_v1_player_profile_rows,
)
from app.models import Player, PlayerAction, PlayerActionTimestamp
from tests.utils.utils import random_steamid64


def _write_player_dump(path: Path, rows: list[str]) -> Path:
    header = (
        "COPY public.player (steamid64, name, custom_id, avatar_hash, country, "
        "created_at, last_seen, alias, updated_at, profile_updated_at, primary_mode, "
        "is_country_locked, alias_updated_at) FROM stdin;\n"
    )
    path.write_text(header + "\n".join(rows) + "\n\\.\n", encoding="utf-8")
    return path


def _player_dump_row(
    *,
    steamid64: int,
    country: str = r"\N",
    alias: str = r"\N",
    created_at: str = r"\N",
    updated_at: str = r"\N",
    is_country_locked: str = "f",
    alias_updated_at: str = r"\N",
) -> str:
    return "\t".join(
        [
            str(steamid64),
            "Steam Name",
            r"\N",
            r"\N",
            country,
            created_at,
            r"\N",
            alias,
            updated_at,
            r"\N",
            "KZT",
            is_country_locked,
            alias_updated_at,
        ]
    )


def test_iter_v1_player_profile_rows_parses_copy_values(tmp_path: Path) -> None:
    dump_path = _write_player_dump(
        tmp_path / "players.sql",
        [
            _player_dump_row(
                steamid64=76561198000000001,
                country="us",
                alias=r"Alias\tWith\\Slash",
                created_at="2026-01-01 01:02:03",
                updated_at="2026-01-02 01:02:03+00",
                is_country_locked="t",
                alias_updated_at="2026-01-03 01:02:03+00",
            ),
            _player_dump_row(steamid64=76561198000000002),
        ],
    )

    rows = list(iter_v1_player_profile_rows(dump_path))

    assert len(rows) == 2
    assert rows[0].steamid64 == 76561198000000001
    assert rows[0].country == "US"
    assert rows[0].alias == "Alias\tWith\\Slash"
    assert rows[0].created_at == datetime(2026, 1, 1, 1, 2, 3, tzinfo=UTC)
    assert rows[0].updated_at == datetime(2026, 1, 2, 1, 2, 3, tzinfo=UTC)
    assert rows[0].is_country_locked is True
    assert rows[0].alias_updated_at == datetime(2026, 1, 3, 1, 2, 3, tzinfo=UTC)
    assert rows[1].alias is None
    assert rows[1].country is None


def test_iter_v1_player_profile_rows_rejects_malformed_rows(tmp_path: Path) -> None:
    dump_path = _write_player_dump(
        tmp_path / "players.sql",
        ["76561198000000001\ttoo-few-fields"],
    )

    with pytest.raises(ValueError, match="expected 13 fields"):
        list(iter_v1_player_profile_rows(dump_path))


@pytest.mark.asyncio
async def test_import_updates_existing_players_and_actions(
    db: AsyncSession,
    tmp_path: Path,
) -> None:
    matched_locked = random_steamid64()
    matched_unlocked = random_steamid64()
    missing = random_steamid64()
    existing_alias_changed_at = datetime(2026, 1, 1, tzinfo=UTC)

    db.add_all(
        [
            Player(
                steamid64=matched_locked,
                name="Matched Locked",
                alias="Old Alias",
                country="CA",
            ),
            Player(
                steamid64=matched_unlocked,
                name="Matched Unlocked",
                alias="Old Unlocked",
                country="US",
            ),
            PlayerActionTimestamp(
                player_steamid64=matched_unlocked,
                action=PlayerAction.COUNTRY_MANUAL_OVERRIDE,
                recorded_at=existing_alias_changed_at,
            ),
        ]
    )
    await db.commit()

    dump_path = _write_player_dump(
        tmp_path / "players.sql",
        [
            _player_dump_row(
                steamid64=matched_locked,
                country="de",
                alias="New Locked Alias That Is Too Long",
                created_at="2026-02-01 00:00:00+00",
                updated_at="2026-02-02 00:00:00+00",
                is_country_locked="t",
                alias_updated_at="2026-02-03 00:00:00+00",
            ),
            _player_dump_row(
                steamid64=matched_unlocked,
                country=r"\N",
                alias="Unlocked Alias",
                is_country_locked="f",
            ),
            _player_dump_row(
                steamid64=missing,
                country="FR",
                alias="Missing Player",
                is_country_locked="t",
            ),
        ],
    )

    summary = await import_v1_player_profile_fields(
        session=db,
        dump_path=dump_path,
        dry_run=False,
        batch_size=2,
    )

    assert summary.source_rows == 3
    assert summary.matched_rows == 2
    assert summary.skipped_missing_players == 1
    assert summary.alias_changed_rows == 2
    assert summary.country_changed_rows == 2
    assert summary.country_lock_upsert_rows == 1
    assert summary.country_lock_delete_rows == 1
    assert summary.alias_action_upsert_rows == 1
    assert summary.truncated_alias_rows == 1

    locked_player = await db.get(Player, matched_locked)
    unlocked_player = await db.get(Player, matched_unlocked)
    assert locked_player is not None
    assert unlocked_player is not None
    assert locked_player.alias == "New Locked Alias That Is"
    assert locked_player.country == "DE"
    assert unlocked_player.alias == "Unlocked Alias"
    assert unlocked_player.country is None
    assert await db.get(Player, missing) is None

    country_lock_rows = (
        await db.exec(
            select(PlayerActionTimestamp).where(
                PlayerActionTimestamp.action == PlayerAction.COUNTRY_MANUAL_OVERRIDE
            )
        )
    ).all()
    assert [(row.player_steamid64, row.recorded_at) for row in country_lock_rows] == [
        (matched_locked, datetime(2026, 2, 2, tzinfo=UTC))
    ]
    alias_action = await db.get(
        PlayerActionTimestamp,
        (matched_locked, PlayerAction.ALIAS_CHANGE),
    )
    assert alias_action is not None
    assert alias_action.recorded_at == datetime(2026, 2, 3, tzinfo=UTC)


@pytest.mark.asyncio
async def test_import_dry_run_rolls_back_changes(
    db: AsyncSession,
    tmp_path: Path,
) -> None:
    steamid64 = random_steamid64()
    db.add(Player(steamid64=steamid64, name="Dry Run", alias="Before", country="US"))
    await db.commit()

    dump_path = _write_player_dump(
        tmp_path / "players.sql",
        [
            _player_dump_row(
                steamid64=steamid64,
                country="JP",
                alias="After",
                is_country_locked="t",
                updated_at="2026-02-02 00:00:00+00",
            )
        ],
    )

    summary = await import_v1_player_profile_fields(
        session=db,
        dump_path=dump_path,
        dry_run=True,
    )

    assert summary.dry_run is True
    assert summary.alias_changed_rows == 1
    assert summary.country_changed_rows == 1
    assert summary.country_lock_upsert_rows == 1

    player = await db.get(Player, steamid64)
    assert player is not None
    assert player.alias == "Before"
    assert player.country == "US"
    action_count = (
        await db.execute(
            text(
                """
                SELECT count(*)
                FROM player_action_timestamp
                WHERE player_steamid64 = :steamid64
                """
            ),
            {"steamid64": steamid64},
        )
    ).scalar_one()
    assert action_count == 0
