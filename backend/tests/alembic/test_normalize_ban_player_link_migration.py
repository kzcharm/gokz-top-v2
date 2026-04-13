from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlmodel import Session

from app.core.db import engine


def _load_migration_module() -> Any:
    path = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "alembic"
        / "versions"
        / "438918b4fdc5_normalize_ban_player_link.py"
    )
    spec = importlib.util.spec_from_file_location("normalize_ban_player_link", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _scratch_table_name(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def test_backfill_players_from_bans_creates_missing_players_and_preserves_existing() -> None:
    migration = _load_migration_module()
    player_table = _scratch_table_name("test_ban_player_link_player")
    ban_table = _scratch_table_name("test_ban_player_link_ban")

    with Session(engine) as session:
        try:
            session.exec(
                text(
                    f"""
                    CREATE TABLE "{player_table}" (
                        steamid64 BIGINT PRIMARY KEY,
                        name VARCHAR(255) NOT NULL,
                        is_country_locked BOOLEAN NOT NULL,
                        created_at TIMESTAMPTZ NULL,
                        last_played_at TIMESTAMPTZ NULL,
                        updated_at TIMESTAMPTZ NULL
                    )
                    """
                )
            )
            session.exec(
                text(
                    f"""
                    CREATE TABLE "{ban_table}" (
                        id INTEGER PRIMARY KEY,
                        steamid64 BIGINT NOT NULL,
                        player_name VARCHAR(255) NULL,
                        created_at TIMESTAMPTZ NOT NULL
                    )
                    """
                )
            )
            session.exec(
                text(
                    f"""
                    INSERT INTO "{player_table}" (
                        steamid64, name, is_country_locked, created_at, last_played_at, updated_at
                    ) VALUES (
                        76561198000000022,
                        'Existing Player',
                        FALSE,
                        TIMESTAMPTZ '2026-03-01 00:00:00+00',
                        NULL,
                        TIMESTAMPTZ '2026-03-02 00:00:00+00'
                    )
                    """
                )
            )
            session.exec(
                text(
                    f"""
                    INSERT INTO "{ban_table}" (id, steamid64, player_name, created_at)
                    VALUES
                        (
                            1,
                            76561198000000011,
                            '',
                            TIMESTAMPTZ '2026-04-02 00:00:00+00'
                        ),
                        (
                            2,
                            76561198000000011,
                            'Recovered Name',
                            TIMESTAMPTZ '2026-04-01 00:00:00+00'
                        ),
                        (
                            3,
                            76561198000000022,
                            'Should Not Replace',
                            TIMESTAMPTZ '2026-04-03 00:00:00+00'
                        )
                    """
                )
            )
            session.commit()

            migration._backfill_players_from_bans(
                session.connection(),
                ban_table=ban_table,
                player_table=player_table,
            )
            session.commit()

            rows = session.exec(
                text(
                    f"""
                    SELECT steamid64, name, created_at, last_played_at
                    FROM "{player_table}"
                    ORDER BY steamid64
                    """
                )
            ).all()

            assert len(rows) == 2
            assert rows[0].steamid64 == 76561198000000011
            assert rows[0].name == "Recovered Name"
            assert str(rows[0].created_at) == "2026-04-01 00:00:00+00:00"
            assert rows[0].last_played_at is None
            assert rows[1].steamid64 == 76561198000000022
            assert rows[1].name == "Existing Player"
        finally:
            session.exec(text(f'DROP TABLE IF EXISTS "{ban_table}"'))
            session.exec(text(f'DROP TABLE IF EXISTS "{player_table}"'))
            session.commit()


def test_restore_ban_player_fields_uses_player_name_and_steamid_fallback() -> None:
    migration = _load_migration_module()
    player_table = _scratch_table_name("test_ban_restore_player")
    ban_table = _scratch_table_name("test_ban_restore_ban")

    with Session(engine) as session:
        try:
            session.exec(
                text(
                    f"""
                    CREATE TABLE "{player_table}" (
                        steamid64 BIGINT PRIMARY KEY,
                        name VARCHAR(255) NOT NULL
                    )
                    """
                )
            )
            session.exec(
                text(
                    f"""
                    CREATE TABLE "{ban_table}" (
                        id INTEGER PRIMARY KEY,
                        steamid64 BIGINT NOT NULL,
                        player_name VARCHAR(255) NULL,
                        steam_id VARCHAR(32) NULL
                    )
                    """
                )
            )
            session.exec(
                text(
                    f"""
                    INSERT INTO "{player_table}" (steamid64, name)
                    VALUES (76561198000000111, 'Linked Player')
                    """
                )
            )
            session.exec(
                text(
                    f"""
                    INSERT INTO "{ban_table}" (id, steamid64, player_name, steam_id)
                    VALUES
                        (1, 76561198000000111, NULL, NULL),
                        (2, 76561198000000222, '', NULL)
                    """
                )
            )
            session.commit()

            migration._restore_ban_player_fields(
                session.connection(),
                ban_table=ban_table,
                player_table=player_table,
            )
            session.commit()

            rows = session.exec(
                text(
                    f"""
                    SELECT id, player_name, steam_id
                    FROM "{ban_table}"
                    ORDER BY id
                    """
                )
            ).all()

            assert rows[0].player_name == "Linked Player"
            assert rows[0].steam_id == "76561198000000111"
            assert rows[1].player_name == "76561198000000222"
            assert rows[1].steam_id == "76561198000000222"
        finally:
            session.exec(text(f'DROP TABLE IF EXISTS "{ban_table}"'))
            session.exec(text(f'DROP TABLE IF EXISTS "{player_table}"'))
            session.commit()
