"""Prove legacy answer preservation under real PostgreSQL DDL, isolated CI only."""
import asyncio
import importlib.util
import os
import uuid
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.models import User, UserQuestion


async def main():
    url = os.environ['DATABASE_URL']
    if make_url(url).database != 'era_test':
        raise RuntimeError('Only isolated era_test is allowed')
    path = Path(__file__).resolve().parents[1] / 'alembic/versions/0062_support_threads.py'
    spec = importlib.util.spec_from_file_location('support_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_async_engine(url)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            user = User(telegram_id=11_000_000_000 + int(uuid.uuid4().hex[:7], 16), first_name='CI migration')
            session.add(user)
            await session.flush()
            question = UserQuestion(user_id=user.id, text='Legacy question', status='answered', admin_answer='Legacy delivered answer')
            session.add(question)
            await session.commit()
            item_id = question.id
        async with engine.begin() as connection:
            def probe(sync_connection):
                with Operations.context(MigrationContext.configure(sync_connection)):
                    migration.downgrade()
                    before = sync_connection.execute(text('SELECT text, status, admin_answer FROM user_questions WHERE id=:id'),
                        {'id': item_id}).one()
                    assert before == ('Legacy question', 'answered', 'Legacy delivered answer')
                    migration.upgrade()
                    migration.upgrade()
                    after = sync_connection.execute(text('SELECT text, status, admin_answer, thread_revision FROM user_questions WHERE id=:id'),
                        {'id': item_id}).one()
                    assert after == (*before, 0)
            await connection.run_sync(probe)
        print('PostgreSQL support migration: legacy question IDs and delivered answer preserved; clean upgrade and repeated upgrade pass')
    finally:
        await engine.dispose()


if __name__ == '__main__':
    asyncio.run(main())
