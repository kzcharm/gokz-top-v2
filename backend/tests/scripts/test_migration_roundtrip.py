"""Exercise the complete migration chain in a database owned by this test."""

import uuid
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from psycopg import sql
from sqlalchemy import create_engine, inspect, text

from app.core.config import settings


@pytest.mark.parametrize("revision", ["head", "314e5fb23acc"])
def test_migrations_upgrade_downgrade_and_upgrade_again(
    monkeypatch, revision: str
) -> None:
    database_name = f"test_migration_roundtrip_{uuid.uuid7().hex}"
    connection_options = {
        "host": settings.POSTGRES_SERVER,
        "port": settings.POSTGRES_PORT,
        "user": settings.POSTGRES_USER,
        "password": settings.POSTGRES_PASSWORD,
        "dbname": "postgres",
        "autocommit": True,
    }
    with psycopg.connect(**connection_options) as admin:
        admin.execute(
            sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name))
        )
    try:
        monkeypatch.setattr(settings, "POSTGRES_DB", database_name)
        config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
        command.upgrade(config, revision)
        engine = create_engine(str(settings.SQLALCHEMY_DATABASE_URI))
        try:
            with engine.connect() as connection:
                assert {"record", "player", "server_group"}.issubset(
                    inspect(connection).get_table_names()
                )
                if revision == "head":
                    assert "recent_wr_events" in inspect(connection).get_table_names(
                        schema="cache"
                    )
            # The mode/scope enum cutover is deliberately irreversible.
            # Verify both supported rollback segments and its explicit guard.
            rollback_target = "79409830f127" if revision == "head" else "base"
            command.downgrade(config, rollback_target)
            with engine.connect() as connection:
                if revision == "head":
                    assert (
                        connection.execute(
                            text("SELECT version_num FROM alembic_version")
                        ).scalar_one()
                        == rollback_target
                    )
                else:
                    assert inspect(connection).get_table_names() == ["alembic_version"]
            if revision == "head":
                with pytest.raises(RuntimeError, match="Downgrade is not supported"):
                    command.downgrade(config, "314e5fb23acc")
            command.upgrade(config, revision)
            with engine.connect() as connection:
                assert (
                    connection.execute(text("SELECT COUNT(*) FROM record")).scalar_one()
                    == 0
                )
        finally:
            engine.dispose()
    finally:
        # Only this freshly created, uniquely named database belongs to the test.
        with psycopg.connect(**connection_options) as admin:
            admin.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(
                    sql.Identifier(database_name)
                )
            )
