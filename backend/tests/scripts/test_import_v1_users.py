from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.importers.v1_users import (
    import_v1_users,
    iter_v1_user_player_rows,
    iter_v1_user_rows,
)
from app.models import Player, User, UserRole
from tests.utils.utils import random_steamid64


def _write_v1_dump(path: Path, *, player_rows: list[str], user_rows: list[str]) -> Path:
    player_header = (
        "COPY public.player (steamid64, name, custom_id, avatar_hash, country, "
        "created_at, last_seen, alias, updated_at, profile_updated_at, primary_mode, "
        "is_country_locked, alias_updated_at) FROM stdin;\n"
    )
    user_header = (
        'COPY public."user" (is_active, is_superuser, id, steamid64, created_at, '
        "last_seen, default_mode, default_page) FROM stdin;\n"
    )
    player_body = "".join(f"{row}\n" for row in player_rows)
    user_body = "".join(f"{row}\n" for row in user_rows)
    path.write_text(
        player_header
        + player_body
        + "\\.\n"
        + user_header
        + user_body
        + "\\.\n",
        encoding="utf-8",
    )
    return path


def _player_dump_row(
    *,
    steamid64: int,
    name: str = "Steam Name",
    country: str = r"\N",
    created_at: str = r"\N",
    last_seen: str = r"\N",
    alias: str = r"\N",
    updated_at: str = r"\N",
) -> str:
    return "\t".join(
        [
            str(steamid64),
            name,
            r"\N",
            r"\N",
            country,
            created_at,
            last_seen,
            alias,
            updated_at,
            r"\N",
            "KZT",
            "f",
            r"\N",
        ]
    )


def _user_dump_row(
    *,
    steamid64: int,
    is_active: str = "t",
    is_superuser: str = "f",
    created_at: str = r"\N",
    last_seen: str = r"\N",
) -> str:
    return "\t".join(
        [
            is_active,
            is_superuser,
            "4b6c370c-6e92-4b6f-b6cc-92404f26a782",
            str(steamid64),
            created_at,
            last_seen,
            "KZT",
            "profile",
        ]
    )


def test_iter_v1_user_rows_parses_copy_values(tmp_path: Path) -> None:
    steamid64 = random_steamid64()
    dump_path = _write_v1_dump(
        tmp_path / "v1.sql",
        player_rows=[],
        user_rows=[
            _user_dump_row(
                steamid64=steamid64,
                is_active="f",
                is_superuser="t",
                created_at="2026-01-01 01:02:03",
                last_seen="2026-01-02 01:02:03+00",
            )
        ],
    )

    rows = list(iter_v1_user_rows(dump_path))

    assert len(rows) == 1
    assert rows[0].steamid64 == steamid64
    assert rows[0].created_at == datetime(2026, 1, 1, 1, 2, 3, tzinfo=UTC)
    assert rows[0].last_seen == datetime(2026, 1, 2, 1, 2, 3, tzinfo=UTC)


def test_iter_v1_user_player_rows_parses_copy_values(tmp_path: Path) -> None:
    steamid64 = random_steamid64()
    dump_path = _write_v1_dump(
        tmp_path / "v1.sql",
        player_rows=[
            _player_dump_row(
                steamid64=steamid64,
                name=r"Name\tWith\\Slash",
                country="us",
                created_at="2026-01-01 01:02:03",
                last_seen="2026-01-02 01:02:03+00",
                alias="Alias",
                updated_at="2026-01-03 01:02:03+00",
            )
        ],
        user_rows=[],
    )

    rows = list(iter_v1_user_player_rows(dump_path))

    assert len(rows) == 1
    assert rows[0].steamid64 == steamid64
    assert rows[0].name == "Name\tWith\\Slash"
    assert rows[0].country == "US"
    assert rows[0].alias == "Alias"
    assert rows[0].created_at == datetime(2026, 1, 1, 1, 2, 3, tzinfo=UTC)
    assert rows[0].last_seen == datetime(2026, 1, 2, 1, 2, 3, tzinfo=UTC)
    assert rows[0].updated_at == datetime(2026, 1, 3, 1, 2, 3, tzinfo=UTC)


def test_iter_v1_user_rows_rejects_malformed_rows(tmp_path: Path) -> None:
    dump_path = _write_v1_dump(
        tmp_path / "v1.sql",
        player_rows=[],
        user_rows=["t\tf\ttoo-few-fields"],
    )

    with pytest.raises(ValueError, match="expected 8 fields"):
        list(iter_v1_user_rows(dump_path))


@pytest.mark.asyncio
async def test_import_inserts_missing_users_without_roles(
    db: AsyncSession,
    tmp_path: Path,
) -> None:
    steamid64 = random_steamid64()
    dump_path = _write_v1_dump(
        tmp_path / "v1.sql",
        player_rows=[
            _player_dump_row(
                steamid64=steamid64,
                name="Imported Player",
                country="DE",
                alias="Imported Alias That Is Too Long",
                created_at="2026-01-01 00:00:00+00",
                last_seen="2026-01-05 00:00:00+00",
                updated_at="2026-01-06 00:00:00+00",
            )
        ],
        user_rows=[
            _user_dump_row(
                steamid64=steamid64,
                is_active="f",
                is_superuser="t",
                created_at="2026-01-02 00:00:00+00",
                last_seen="2026-01-07 00:00:00+00",
            )
        ],
    )

    summary = await import_v1_users(
        session=db,
        dump_path=dump_path,
        dry_run=False,
        batch_size=1,
    )

    assert summary.source_users == 1
    assert summary.inserted_users == 1
    assert summary.missing_players == 1
    assert summary.player_source_rows_for_missing_players == 1
    assert summary.fallback_players == 0
    assert summary.created_players == 1

    user = await db.get(User, steamid64)
    player = await db.get(Player, steamid64)
    assert user is not None
    assert player is not None
    assert user.is_active is True
    assert user.roles == []
    assert user.created_at == datetime(2026, 1, 2, tzinfo=UTC)
    assert user.last_visited_at == datetime(2026, 1, 7, tzinfo=UTC)
    assert player.name == "Imported Player"
    assert player.alias == "Imported Alias That Is To"
    assert player.country == "DE"


@pytest.mark.asyncio
async def test_import_reconciles_existing_user_timestamps_and_preserves_state(
    db: AsyncSession,
    tmp_path: Path,
) -> None:
    steamid64 = random_steamid64()
    db.add(Player(steamid64=steamid64, name="Existing Player"))
    db.add(
        User(
            steamid64=steamid64,
            is_active=False,
            roles=[UserRole.SUPERUSER, UserRole.MAP_ADMIN],
            created_at=datetime(2026, 1, 10, tzinfo=UTC),
            last_visited_at=datetime(2026, 1, 5, tzinfo=UTC),
        )
    )
    await db.commit()

    dump_path = _write_v1_dump(
        tmp_path / "v1.sql",
        player_rows=[_player_dump_row(steamid64=steamid64, name="Ignored Player")],
        user_rows=[
            _user_dump_row(
                steamid64=steamid64,
                is_active="t",
                is_superuser="f",
                created_at="2026-01-01 00:00:00+00",
                last_seen="2026-01-20 00:00:00+00",
            )
        ],
    )

    summary = await import_v1_users(session=db, dump_path=dump_path, dry_run=False)

    assert summary.inserted_users == 0
    assert summary.timestamp_updated_users == 1
    assert summary.missing_players == 0

    user = await db.get(User, steamid64)
    player = await db.get(Player, steamid64)
    assert user is not None
    assert player is not None
    assert user.is_active is False
    assert user.roles == [UserRole.SUPERUSER, UserRole.MAP_ADMIN]
    assert user.created_at == datetime(2026, 1, 1, tzinfo=UTC)
    assert user.last_visited_at == datetime(2026, 1, 20, tzinfo=UTC)
    assert player.name == "Existing Player"


@pytest.mark.asyncio
async def test_import_creates_fallback_player_for_user_without_player_source(
    db: AsyncSession,
    tmp_path: Path,
) -> None:
    steamid64 = random_steamid64()
    dump_path = _write_v1_dump(
        tmp_path / "v1.sql",
        player_rows=[],
        user_rows=[_user_dump_row(steamid64=steamid64)],
    )

    summary = await import_v1_users(session=db, dump_path=dump_path, dry_run=False)

    assert summary.inserted_users == 1
    assert summary.missing_players == 1
    assert summary.player_source_rows_for_missing_players == 0
    assert summary.fallback_players == 1

    player = await db.get(Player, steamid64)
    assert player is not None
    assert player.name == str(steamid64)


@pytest.mark.asyncio
async def test_import_is_idempotent_and_dry_run_rolls_back(
    db: AsyncSession,
    tmp_path: Path,
) -> None:
    steamid64 = random_steamid64()
    dump_path = _write_v1_dump(
        tmp_path / "v1.sql",
        player_rows=[_player_dump_row(steamid64=steamid64)],
        user_rows=[
            _user_dump_row(
                steamid64=steamid64,
                created_at="2026-01-01 00:00:00+00",
                last_seen="2026-01-02 00:00:00+00",
            )
        ],
    )

    dry_run_summary = await import_v1_users(
        session=db,
        dump_path=dump_path,
        dry_run=True,
    )

    assert dry_run_summary.dry_run is True
    assert dry_run_summary.inserted_users == 1
    assert await db.get(User, steamid64) is None

    first_summary = await import_v1_users(
        session=db,
        dump_path=dump_path,
        dry_run=False,
    )
    second_summary = await import_v1_users(
        session=db,
        dump_path=dump_path,
        dry_run=False,
    )

    assert first_summary.inserted_users == 1
    assert first_summary.created_players == 1
    assert second_summary.inserted_users == 0
    assert second_summary.created_players == 0
    assert second_summary.timestamp_updated_users == 0
