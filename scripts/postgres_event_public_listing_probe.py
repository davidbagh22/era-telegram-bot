"""PostgreSQL 18 rehearsal for the reversible public-listing migration.

CI-only: operates in a transaction-local synthetic schema and rolls back all DDL.
Never point this probe at production or an externally reachable database.
"""
from __future__ import annotations

import asyncio
import importlib.util
import os
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.ext.asyncio import create_async_engine

EXPECTED_URL = "postgresql+asyncpg://era_test:era_test@127.0.0.1:5432/era_test"


def rehearse(connection: sa.Connection) -> None:
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "0065_event_public_listing.py"
    )
    spec = importlib.util.spec_from_file_location(
        "era_visibility_pg18_migration_probe", migration_path
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    migration.op = Operations(MigrationContext.configure(connection))

    version = int(connection.exec_driver_sql("SHOW server_version_num").scalar_one())
    assert 180000 <= version < 190000, f"Expected disposable PostgreSQL 18, got {version}"

    # Transactional schema creation means the entire fixture disappears on rollback.
    connection.exec_driver_sql("CREATE SCHEMA era_visibility_ci_probe")
    connection.exec_driver_sql(
        "SET LOCAL search_path TO era_visibility_ci_probe, public"
    )
    assert connection.exec_driver_sql("SELECT current_schema()").scalar_one() == "era_visibility_ci_probe"

    # Existing event metadata and registration records are synthetic and isolated.
    connection.exec_driver_sql(
        "CREATE TABLE event_experiences "
        "(event_id INTEGER PRIMARY KEY, note TEXT NOT NULL)"
    )
    connection.exec_driver_sql(
        "CREATE TABLE event_registrations "
        "(id INTEGER PRIMARY KEY, event_id INTEGER NOT NULL)"
    )
    connection.exec_driver_sql(
        "INSERT INTO event_experiences (event_id, note) VALUES (7, 'retain')"
    )
    connection.exec_driver_sql(
        "INSERT INTO event_registrations (id, event_id) VALUES (13, 7)"
    )

    migration.upgrade()
    old = connection.exec_driver_sql(
        "SELECT event_id, note, show_in_public_listing "
        "FROM event_experiences WHERE event_id = 7"
    ).one()
    assert tuple(old) == (7, "retain", True), old
    # Server default applies to rows inserted after migration, not only old rows.
    connection.exec_driver_sql(
        "INSERT INTO event_experiences (event_id, note) VALUES (8, 'new')"
    )
    assert connection.exec_driver_sql(
        "SELECT show_in_public_listing FROM event_experiences WHERE event_id = 8"
    ).scalar_one() is True

    # Repeated forward execution must never undo a manager's hidden choice.
    connection.exec_driver_sql(
        "UPDATE event_experiences SET show_in_public_listing = false WHERE event_id = 7"
    )
    migration.upgrade()
    assert connection.exec_driver_sql(
        "SELECT show_in_public_listing FROM event_experiences WHERE event_id = 7"
    ).scalar_one() is False
    assert connection.exec_driver_sql(
        "SELECT count(*) FROM event_registrations WHERE event_id = 7"
    ).scalar_one() == 1

    # Downgrade must fail closed rather than re-exposing deliberately hidden data.
    try:
        migration.downgrade()
    except NotImplementedError:
        pass
    else:
        raise AssertionError("Unsafe visibility-column downgrade was allowed")
    assert connection.exec_driver_sql(
        "SELECT show_in_public_listing FROM event_experiences WHERE event_id = 7"
    ).scalar_one() is False

    # Missing table must be rejected without creating an empty replacement.
    connection.exec_driver_sql("CREATE SCHEMA era_visibility_ci_missing")
    connection.exec_driver_sql(
        "SET LOCAL search_path TO era_visibility_ci_missing, public"
    )
    try:
        migration.upgrade()
    except RuntimeError as exc:
        assert "event_experiences table missing" in str(exc), str(exc)
    else:
        raise AssertionError("Missing-table migration did not fail closed")
    assert "event_experiences" not in sa.inspect(connection).get_table_names()


async def main() -> None:
    url = os.environ.get("DATABASE_URL")
    if url != EXPECTED_URL or os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("Only the disposable local PostgreSQL 18 GitHub CI database is allowed")
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                await connection.run_sync(rehearse)
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()
    print("PostgreSQL 18 synthetic visibility migration: retention, default, idempotency and fail-closed rollback PASS")


if __name__ == "__main__":
    asyncio.run(main())
