import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text


def test_support_migration_preserves_legacy_and_refuses_destructive_downgrade():
    path = Path(__file__).resolve().parents[1] / 'alembic/versions/0062_support_threads.py'
    spec = importlib.util.spec_from_file_location('support_thread_migration', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = create_engine('sqlite:///:memory:')
    try:
        with engine.begin() as conn:
            conn.execute(text('CREATE TABLE users (id INTEGER PRIMARY KEY)'))
            conn.execute(text('CREATE TABLE user_questions (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), '
                'text TEXT NOT NULL, status VARCHAR(32) NOT NULL, admin_answer TEXT)'))
            conn.execute(text('INSERT INTO users (id) VALUES (1)'))
            conn.execute(text("INSERT INTO user_questions VALUES (1, 1, 'Original', 'answered', 'Delivered answer')"))
            with Operations.context(MigrationContext.configure(conn)):
                module.upgrade()
                assert conn.execute(text('SELECT text, status, admin_answer, thread_revision FROM user_questions')).one() == (
                    'Original', 'answered', 'Delivered answer', 0)
                module.downgrade()
                assert 'thread_revision' not in {c['name'] for c in inspect(conn).get_columns('user_questions')}
                module.upgrade()
                conn.execute(text("INSERT INTO support_messages (question_id, author_id, direction, source_key, text) "
                    "VALUES (1, 1, 'participant', 'unique', 'New reply')"))
                with pytest.raises(RuntimeError, match='retain the additive schema'):
                    module.downgrade()
                assert conn.execute(text('SELECT text FROM support_messages')).scalar() == 'New reply'
                assert conn.execute(text('SELECT admin_answer FROM user_questions')).scalar() == 'Delivered answer'
    finally:
        engine.dispose()
