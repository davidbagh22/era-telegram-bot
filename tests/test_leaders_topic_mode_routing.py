"""Fail-closed routing when a persisted Leaders topic mode is damaged."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import AppSetting
from app.services.leaders_topics_service import delivery_topic, topic_id, setup_leaders_topics


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


    async def test_unconfirmed_thread_state_with_valid_id_never_routes(self):
        from sqlalchemy import delete
        for state in ('creating', 'failed', 'uncertain', False, 7):
            with self.subTest(state=state):
                async with self.factory() as session:
                    await session.execute(delete(AppSetting))
                    session.add(AppSetting(
                        key='leaders_forum:-1001:tasks',
                        value=__import__('json').dumps({
                            'mode': 'forum', 'thread_id': 42, 'thread_state': state,
                        }),
                    ))
                    await session.commit()
                    self.assertIsNone(await topic_id(session, -1001, 'tasks'))
                    with self.assertRaisesRegex(ValueError, 'Создание темы не подтверждено'):
                        await delivery_topic(session, -1001, 'tasks')

    async def test_explicit_ready_thread_state_still_routes(self):
        async with self.factory() as session:
            session.add(AppSetting(
                key='leaders_forum:-1001:tasks',
                value='{"mode":"forum","thread_id":42,"thread_state":"ready"}',
            ))
            await session.commit()
            self.assertEqual(await topic_id(session, -1001, 'tasks'), 42)
            self.assertEqual(await delivery_topic(session, -1001, 'tasks'), 42)

    async def test_setup_does_not_send_or_create_when_thread_state_is_uncertain(self):
        async with self.factory() as session:
            session.add(AppSetting(
                key='leaders_forum:-1001:tasks',
                value='{"mode":"forum","thread_id":42,"thread_state":"failed"}',
            ))
            await session.commit()
        bot = SimpleNamespace(
            get_chat=AsyncMock(return_value=SimpleNamespace(type='supergroup', is_forum=True)),
            get_me=AsyncMock(return_value=SimpleNamespace(id=77, username='ERA_1bot')),
            get_chat_member=AsyncMock(return_value=SimpleNamespace(
                status='administrator', can_manage_topics=True,
            )),
            create_forum_topic=AsyncMock(),
            send_message=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        settings = SimpleNamespace(leaders_chat_id=-1001, general_chat_id=-1002)
        result = await setup_leaders_topics(bot, settings, self.factory)
        self.assertEqual(result, {
            'status': 'topic_needs_review', 'chat_id': -1001, 'topic': 'tasks',
        })
        bot.create_forum_topic.assert_not_awaited()
        bot.send_message.assert_not_awaited()
        bot.edit_message_text.assert_not_awaited()

    async def test_explicit_plain_mode_never_returns_thread(self):
        async with self.factory() as session:
            session.add(AppSetting(key='leaders_forum:-1001:tasks', value='{"mode":"plain","thread_id":null,"message_id":91,"message_state":"sent"}'))
            await session.commit()
            self.assertIsNone(await topic_id(session, -1001, 'tasks'))
            self.assertIsNone(await delivery_topic(session, -1001, 'tasks'))
