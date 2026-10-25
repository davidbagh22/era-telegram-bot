"""Fail-closed routing when a persisted Leaders topic mode is damaged."""
import unittest

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import AppSetting
from app.services.leaders_topics_service import delivery_topic, topic_id


class LeadersTopicModeRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_unknown_mode_with_plausible_thread_id_fails_closed(self):
        from sqlalchemy import delete
        for value in (
            '{"mode":"unexpected","thread_id":42}',
            '{"mode":false,"thread_id":42}',
            '{"mode":123,"thread_id":42}',
        ):
            with self.subTest(value=value):
                async with self.factory() as session:
                    await session.execute(delete(AppSetting))
                    session.add(AppSetting(key='leaders_forum:-1001:tasks', value=value))
                    await session.commit()
                    self.assertIsNone(await topic_id(session, -1001, 'tasks'))
                    with self.assertRaisesRegex(ValueError, 'Режим темы'):
                        await delivery_topic(session, -1001, 'tasks')

    async def test_valid_legacy_and_explicit_forum_modes_still_route(self):
        from sqlalchemy import delete
        for value in ('{"thread_id":42}', '{"mode":"forum","thread_id":42}'):
            with self.subTest(value=value):
                async with self.factory() as session:
                    await session.execute(delete(AppSetting))
                    session.add(AppSetting(key='leaders_forum:-1001:tasks', value=value))
                    await session.commit()
                    self.assertEqual(await topic_id(session, -1001, 'tasks'), 42)
                    self.assertEqual(await delivery_topic(session, -1001, 'tasks'), 42)

    async def test_explicit_plain_mode_never_returns_thread(self):
        async with self.factory() as session:
            session.add(AppSetting(key='leaders_forum:-1001:tasks', value='{"mode":"plain","thread_id":null}'))
            await session.commit()
            self.assertIsNone(await topic_id(session, -1001, 'tasks'))
            self.assertIsNone(await delivery_topic(session, -1001, 'tasks'))
