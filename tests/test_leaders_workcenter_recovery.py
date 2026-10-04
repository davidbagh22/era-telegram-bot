from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock
import unittest

from aiogram.types import Message, Chat, User as TelegramUser, CallbackQuery
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.database.base import Base
from app.config import Settings
from app.handlers.leader_chat_workcenter import router
from app.services.leaders_topics_service import setup_leaders_topics
from app.services.weekly_pulse_cycle_service import create_or_get_cycle


class RecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_assignment_callback_not_swallowed(self):
        handler = next(h for h in router.callback_query.handlers if h.callback.__name__ == 'handle_leaders_task_card_action')
        sender = TelegramUser(id=1, is_bot=False, first_name='A')
        event = CallbackQuery(id='1', from_user=sender, chat_instance='1', data='leaders_task:assign:42')
        self.assertFalse((await handler.check(event))[0])
        self.assertTrue((await handler.check(event.model_copy(update={'data': 'leaders_task:start:42'})))[0])

    async def test_pulse_start_does_not_capture_other_start_payloads(self):
        from datetime import datetime, timezone
        handler = next(h for h in router.message.handlers if h.callback.__name__ == 'connect_pulse_from_deep_link')
        event = Message(message_id=1, date=datetime.now(timezone.utc), chat=Chat(id=1, type='private'), text='/start pulse_connect')
        bot = AsyncMock()
        self.assertTrue((await handler.check(event, bot=bot))[0])
        for text in ['/start', '/start ref_hello', '/start event_3']:
            self.assertFalse((await handler.check(event.model_copy(update={'text': text}), bot=bot))[0])

    async def test_rebind_resets_message_but_preserves_cycle(self):
        async with self.factory() as session:
            cycle = await create_or_get_cycle(session, date_from=date(2026,10,5), date_to=date(2026,10,11), leader_chat_id=-1001)
            cycle.announcement_message_id = 42
            again = await create_or_get_cycle(session, date_from=date(2026,10,5), date_to=date(2026,10,11), leader_chat_id=-1002)
            self.assertEqual(cycle.id, again.id)
            self.assertEqual(again.leader_chat_id, -1002)
            self.assertIsNone(again.announcement_message_id)

    async def test_topics_created_only_once_and_never_in_general(self):
        settings = Settings(bot_token='1234567890:test-token', leaders_chat_id=-1001, general_chat_id=-1002)
        bot = AsyncMock()
        bot.get_chat.return_value = SimpleNamespace(is_forum=True)
        bot.get_me.return_value = SimpleNamespace(id=100, username='era_test')
        bot.get_chat_member.return_value = SimpleNamespace(can_manage_topics=True, can_pin_messages=True)
        bot.create_forum_topic.side_effect = [SimpleNamespace(message_thread_id=x) for x in (2,3,4)]
        bot.send_message.return_value = SimpleNamespace(message_id=5)
        self.assertEqual((await setup_leaders_topics(bot, settings, self.factory))['status'], 'ready')
        await setup_leaders_topics(bot, settings, self.factory)
        self.assertEqual(bot.create_forum_topic.await_count, 3)
        self.assertEqual(bot.send_message.await_count, 3)
        settings.leaders_chat_id = settings.general_chat_id
        self.assertEqual((await setup_leaders_topics(bot, settings, self.factory))['status'], 'not_configured')
