import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

import pytest
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession


def _load_migration_module() -> ModuleType:
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "alembic"
        / "versions"
        / "4b80c2f7a91e_centralize_app_settings.py"
    )
    spec = importlib.util.spec_from_file_location(
        "centralize_app_settings_migration", migration_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _create_temporary_setting_tables(db: AsyncSession) -> None:
    await db.execute(
        text(
            """
            CREATE TEMPORARY TABLE app_setting (
                key TEXT PRIMARY KEY,
                value JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL
            ) ON COMMIT DROP
            """
        )
    )
    await db.execute(
        text(
            """
            CREATE TEMPORARY TABLE qq_binding_secret (
                id INTEGER PRIMARY KEY,
                encrypted_secret TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL
            ) ON COMMIT DROP
            """
        )
    )


@pytest.mark.asyncio
async def test_qq_secret_migration_round_trip_preserves_value_and_timestamps(
    db: AsyncSession,
) -> None:
    migration = _load_migration_module()
    await _create_temporary_setting_tables(db)
    created_at = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    updated_at = datetime(2026, 2, 3, 4, 5, 6, tzinfo=UTC)
    await db.execute(
        text(
            """
            INSERT INTO qq_binding_secret (
                id, encrypted_secret, created_at, updated_at
            ) VALUES (1, :secret, :created_at, :updated_at)
            """
        ),
        {
            "secret": "encrypted-value",
            "created_at": created_at,
            "updated_at": updated_at,
        },
    )

    await db.execute(text(migration.UPGRADE_QQ_BINDING_SECRET_SQL))
    migrated = (
        await db.execute(
            text(
                """
                SELECT value, created_at, updated_at
                FROM app_setting
                WHERE key = 'qq_binding_secret'
                """
            )
        )
    ).one()
    assert migrated.value == {"encrypted_secret": "encrypted-value"}
    assert migrated.created_at == created_at
    assert migrated.updated_at == updated_at

    await db.execute(text("DELETE FROM qq_binding_secret"))
    await db.execute(text(migration.DOWNGRADE_QQ_BINDING_SECRET_SQL))
    restored = (
        await db.execute(
            text(
                """
                SELECT encrypted_secret, created_at, updated_at
                FROM qq_binding_secret
                WHERE id = 1
                """
            )
        )
    ).one()
    assert restored.encrypted_secret == "encrypted-value"
    assert restored.created_at == created_at
    assert restored.updated_at == updated_at


@pytest.mark.asyncio
async def test_qq_secret_migration_handles_unconfigured_state(
    db: AsyncSession,
) -> None:
    migration = _load_migration_module()
    await _create_temporary_setting_tables(db)

    await db.execute(text(migration.UPGRADE_QQ_BINDING_SECRET_SQL))
    app_setting_count = (
        await db.execute(text("SELECT count(*) FROM app_setting"))
    ).scalar_one()
    assert app_setting_count == 0

    await db.execute(text(migration.DOWNGRADE_QQ_BINDING_SECRET_SQL))
    legacy_count = (
        await db.execute(text("SELECT count(*) FROM qq_binding_secret"))
    ).scalar_one()
    assert legacy_count == 0
