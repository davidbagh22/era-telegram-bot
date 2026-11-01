"""Disposable SQLite guard for the reversible event-public-listing migration.

This is not a PostgreSQL 18 upgrade/rollback proof or owner approval.
No production database, event, registration, attendance or points are touched.
"""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


class EventPublicListingMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        migration_path = (
            Path(__file__).resolve().parents[1]
            / "alembic"
            / "versions"
            / "0065_event_public_listing.py"
        )
        spec = importlib.util.spec_from_file_location(
            "event_public_listing_migration_under_test", migration_path,
        )
        assert spec is not None and spec.loader is not None
        cls.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.migration)

    def test_upgrade_preserves_existing_row_and_repeat_keeps_hidden_choice(self):
        engine = sa.create_engine("sqlite+pysqlite:///:memory:")
        try:
            with engine.begin() as connection:
                connection.exec_driver_sql(
                    "CREATE TABLE event_experiences "
                    "(event_id INTEGER PRIMARY KEY, note TEXT NOT NULL)"
                )
                connection.exec_driver_sql(
                    "INSERT INTO event_experiences (event_id, note) "
                    "VALUES (7, 'keep-me')"
                )
                self.migration.op = Operations(MigrationContext.configure(connection))
                self.migration.upgrade()
                row = connection.exec_driver_sql(
                    "SELECT event_id, note, show_in_public_listing "
                    "FROM event_experiences"
                ).one()
                self.assertEqual(tuple(row), (7, "keep-me", 1))

                connection.exec_driver_sql(
                    "UPDATE event_experiences SET show_in_public_listing = 0 "
                    "WHERE event_id = 7"
                )
                self.migration.upgrade()
                self.assertEqual(
                    connection.exec_driver_sql(
                        "SELECT count(*) FROM event_experiences"
                    ).scalar_one(),
                    1,
                )
                self.assertEqual(
                    connection.exec_driver_sql(
                        "SELECT show_in_public_listing FROM event_experiences "
                        "WHERE event_id = 7"
                    ).scalar_one(),
                    0,
                )
                # Dropping the column would expose intentionally hidden events.
                with self.assertRaises(NotImplementedError):
                    self.migration.downgrade()
                self.assertEqual(
                    connection.exec_driver_sql(
                        "SELECT show_in_public_listing FROM event_experiences "
                        "WHERE event_id = 7"
                    ).scalar_one(),
                    0,
                )
        finally:
            engine.dispose()

    def test_missing_table_fails_closed_without_creating_data(self):
        engine = sa.create_engine("sqlite+pysqlite:///:memory:")
        try:
            with engine.begin() as connection:
                self.migration.op = Operations(MigrationContext.configure(connection))
                with self.assertRaisesRegex(
                    RuntimeError, "event_experiences table missing",
                ):
                    self.migration.upgrade()
                self.assertNotIn(
                    "event_experiences", sa.inspect(connection).get_table_names(),
                )
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
