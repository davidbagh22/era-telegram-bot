"""Regression coverage for admin-survey production timestamp defaults."""

from __future__ import annotations

import importlib.util
from pathlib import Path


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "0036_admin_survey_timestamps.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "migration_0036_admin_survey_timestamps", MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_upgrade_adds_server_timestamp_defaults_to_both_survey_tables(monkeypatch):
    migration = _load_migration()
    statements: list[str] = []

    monkeypatch.setattr(migration, "_is_postgresql", lambda: True)
    monkeypatch.setattr(migration.op, "execute", statements.append)

    migration.upgrade()

    assert statements == [
        "ALTER TABLE admin_surveys ALTER COLUMN created_at SET DEFAULT now()",
        "ALTER TABLE admin_surveys ALTER COLUMN updated_at SET DEFAULT now()",
        "ALTER TABLE admin_survey_responses ALTER COLUMN created_at SET DEFAULT now()",
        "ALTER TABLE admin_survey_responses ALTER COLUMN updated_at SET DEFAULT now()",
    ]


def test_upgrade_is_noop_outside_postgresql(monkeypatch):
    migration = _load_migration()
    statements: list[str] = []

    monkeypatch.setattr(migration, "_is_postgresql", lambda: False)
    monkeypatch.setattr(migration.op, "execute", statements.append)

    migration.upgrade()

    assert statements == []
