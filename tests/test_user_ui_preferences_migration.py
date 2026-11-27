"""Disposable SQLite guard for the additive, reversible 0070 migration."""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


class UserUiPreferencesMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0070_user_ui_preferences.py"
        spec = importlib.util.spec_from_file_location("ui_prefs_migration_under_test", path)
        assert spec is not None and spec.loader is not None
        cls.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.migration)

    def _bind(self, connection) -> None:
        self.migration.op = Operations(MigrationContext.configure(connection))

    def test_upgrade_is_idempotent_and_downgrade_reverses(self) -> None:
        engine = sa.create_engine("sqlite+pysqlite:///:memory:")
        try:
            with engine.begin() as connection:
                connection.exec_driver_sql("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
                connection.exec_driver_sql("INSERT INTO users (id, name) VALUES (1, 'keep-me')")
                self._bind(connection)
                self.migration.upgrade()
                self.migration.upgrade()
                columns = {c["name"] for c in sa.inspect(connection).get_columns("user_ui_preferences")}
                self.assertEqual(columns, {"user_id", "accent_color", "updated_at"})
                connection.exec_driver_sql("INSERT INTO user_ui_preferences (user_id, accent_color) VALUES (1, '#112233')")
                self.migration.downgrade()
                self.assertNotIn("user_ui_preferences", sa.inspect(connection).get_table_names())
                self.migration.downgrade()
                self.assertEqual(connection.exec_driver_sql("SELECT name FROM users").scalar_one(), "keep-me")
                self.migration.upgrade()
                self.assertIn("user_ui_preferences", sa.inspect(connection).get_table_names())
        finally:
            engine.dispose()

    def test_chain_follows_event_public_listing(self) -> None:
        self.assertEqual(self.migration.down_revision, "0069_event_public_listing")
        self.assertLessEqual(len(self.migration.revision), 32)


if __name__ == "__main__":
    unittest.main()
