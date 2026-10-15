import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text


def test_existing_event_drafts_upgrade_without_scheduling_old_announcements():
    path = Path(__file__).resolve().parents[1] / "alembic/versions/0059_event_publication.py"
    spec = importlib.util.spec_from_file_location("event_publication_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE event_experiences (event_id INTEGER PRIMARY KEY)"))
        connection.execute(text("INSERT INTO event_experiences (event_id) VALUES (7)"))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            migration.upgrade()
        row = connection.execute(text("SELECT event_id, creation_mode, announcement_status FROM event_experiences")).one()
        assert tuple(row) == (7, "wizard", "not_requested")
        assert "ix_event_experiences_announcement_status" in {index["name"] for index in inspect(connection).get_indexes("event_experiences")}
    engine.dispose()
