import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text


def test_notification_message_migration_preserves_old_receipts_and_is_repeatable():
    path = Path(__file__).resolve().parents[1] / 'alembic/versions/0061_notification_message_id.py'
    spec = importlib.util.spec_from_file_location('message_id_migration', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = create_engine('sqlite:///:memory:')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE notification_deliveries (id INTEGER PRIMARY KEY, status VARCHAR(20) NOT NULL)'))
        conn.execute(text("INSERT INTO notification_deliveries (id, status) VALUES (1, 'sent')"))
        with Operations.context(MigrationContext.configure(conn)):
            module.upgrade()
            module.upgrade()
            assert 'message_id' in {column['name'] for column in inspect(conn).get_columns('notification_deliveries')}
            assert conn.execute(text('SELECT status, message_id FROM notification_deliveries WHERE id=1')).one() == ('sent', None)
            conn.execute(text('UPDATE notification_deliveries SET message_id=9223372036854775800 WHERE id=1'))
            assert conn.execute(text('SELECT message_id FROM notification_deliveries WHERE id=1')).scalar() == 9223372036854775800
            module.downgrade()
            module.downgrade()
            assert conn.execute(text('SELECT status FROM notification_deliveries WHERE id=1')).scalar() == 'sent'
    engine.dispose()
