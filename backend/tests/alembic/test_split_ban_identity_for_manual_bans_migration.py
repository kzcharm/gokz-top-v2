from __future__ import annotations

import importlib.util
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlmodel import Session

from app.core.db import engine


def _load_migration_module() -> Any:
    path = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "alembic"
        / "versions"
        / "bcdbe65cef2b_split_ban_identity_for_manual_bans.py"
    )
    spec = importlib.util.spec_from_file_location(
        "split_ban_identity_for_manual_bans",
        path,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _scratch_table_name(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def test_backfill_ban_uuids_assigns_uuid7s_in_created_at_order() -> None:
    migration = _load_migration_module()
    ban_table = _scratch_table_name("test_split_ban_identity_ban")

    with Session(engine) as session:
        try:
            session.exec(
                text(
                    f"""
                    CREATE TABLE "{ban_table}" (
                        id INTEGER NOT NULL PRIMARY KEY,
                        created_at TIMESTAMPTZ NOT NULL,
                        uuid UUID NULL
                    )
                    """
                )
            )
            session.exec(
                text(
                    f"""
                    INSERT INTO "{ban_table}" (id, created_at)
                    VALUES
                        (11, TIMESTAMPTZ '2026-04-01 12:00:00.100+00'),
                        (12, TIMESTAMPTZ '2026-04-01 12:00:00.100+00'),
                        (13, TIMESTAMPTZ '2026-04-01 12:00:00.250+00')
                    """
                )
            )
            session.commit()

            migration._backfill_ban_uuids(
                session.connection(),
                ban_table=ban_table,
            )
            session.commit()

            rows = session.exec(
                text(
                    f"""
                    SELECT id, uuid
                    FROM "{ban_table}"
                    ORDER BY created_at ASC, id ASC
                    """
                )
            ).all()

            assert [row.id for row in rows] == [11, 12, 13]
            parsed = [uuid.UUID(str(row.uuid)) for row in rows]
            assert all(value.version == 7 for value in parsed)
            assert [value.int for value in parsed] == sorted(value.int for value in parsed)
        finally:
            session.exec(text(f'DROP TABLE IF EXISTS "{ban_table}"'))
            session.commit()


def test_downgrade_guard_rejects_manual_bans_without_external_id() -> None:
    migration = _load_migration_module()
    ban_table = _scratch_table_name("test_split_ban_identity_guard")

    with Session(engine) as session:
        try:
            session.exec(
                text(
                    f"""
                    CREATE TABLE "{ban_table}" (
                        id INTEGER NULL
                    )
                    """
                )
            )
            session.exec(
                text(
                    f"""
                    INSERT INTO "{ban_table}" (id)
                    VALUES (NULL)
                    """
                )
            )
            session.commit()

            with pytest.raises(RuntimeError):
                migration._assert_no_manual_bans_without_external_id(
                    session.connection(),
                    ban_table=ban_table,
                )
        finally:
            session.exec(text(f'DROP TABLE IF EXISTS "{ban_table}"'))
            session.commit()
