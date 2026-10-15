import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import BigInteger, create_engine, inspect, text


def test_existing_media_chat_ids_survive_idempotent_bigint_upgrade():
    path = Path(__file__).resolve().parents[1] / "alembic/versions/0060_media_chat_bigint.py"
    spec = importlib.util.spec_from_file_location("media_chat_bigint_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE media_attachments (id INTEGER PRIMARY KEY, source_chat_id INTEGER)"))
        connection.execute(text("CREATE TABLE media_chat_activity (id INTEGER PRIMARY KEY, chat_id INTEGER NOT NULL, UNIQUE(chat_id))"))
        connection.execute(text("CREATE INDEX ix_media_chat_activity_chat_id ON media_chat_activity(chat_id)"))
        chat_id = -1002973371133
        connection.execute(text("INSERT INTO media_attachments VALUES (1, :chat_id), (2, NULL)"), {"chat_id": chat_id})
        connection.execute(text("INSERT INTO media_chat_activity VALUES (1, :chat_id)"), {"chat_id": chat_id})
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            migration.upgrade()
        for table, column in (("media_attachments", "source_chat_id"), ("media_chat_activity", "chat_id")):
            fields = {field["name"]: field for field in inspect(connection).get_columns(table)}
            assert isinstance(fields[column]["type"], BigInteger)
            assert connection.scalar(text(f"SELECT {column} FROM {table} WHERE id=1")) == chat_id
        assert connection.scalar(text("SELECT source_chat_id FROM media_attachments WHERE id=2")) is None
        assert not fields["chat_id"]["nullable"]
        assert inspect(connection).get_unique_constraints("media_chat_activity")
        assert "ix_media_chat_activity_chat_id" in {row["name"] for row in inspect(connection).get_indexes("media_chat_activity")}
    engine.dispose()
