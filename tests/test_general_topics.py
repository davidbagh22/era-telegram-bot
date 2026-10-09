from datetime import datetime
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.database.base import Base
from app.services.general_topics_service import ensure_topic, send_general_topic, setup_general_topics
from app.services.daily_public_content_service import run_daily_public_content
from app.services.general_chat_content_service import deliver_planned_content


class GeneralTopicsTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.settings = Settings(bot_token="1234567890:test-token", general_chat_id=-100123, era_channel_id=-100456)
        self.bot = SimpleNamespace(
            get_chat=AsyncMock(return_value=SimpleNamespace(is_forum=True)),
            get_me=AsyncMock(return_value=SimpleNamespace(id=1, username="ERA_1bot")),
            get_chat_member=AsyncMock(return_value=SimpleNamespace(status="administrator", can_manage_topics=True)),
            create_forum_topic=AsyncMock(side_effect=[SimpleNamespace(message_thread_id=101), SimpleNamespace(message_thread_id=102)]),
            send_message=AsyncMock(),
        )

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_setup_reuses_persisted_topic_ids_after_restart(self):
        first = await setup_general_topics(self.bot, self.settings, self.sessions)
        second = await setup_general_topics(self.bot, self.settings, self.sessions)
        self.assertEqual(first, {"announcements": 101, "notifications": 102})
        self.assertEqual(first, second)
        self.assertEqual(self.bot.create_forum_topic.await_count, 2)
        self.bot.send_message.assert_not_awaited()

    async def test_no_forum_or_permission_never_falls_back_to_general(self):
        self.bot.get_chat.return_value.is_forum = False
        with patch("app.services.general_topics_service._session_factory", return_value=self.sessions):
            self.assertFalse(await send_general_topic(self.bot, self.settings, "notifications", "Hello"))
            self.bot.get_chat.return_value.is_forum = True
            self.bot.get_chat_member.return_value.can_manage_topics = False
            self.assertIsNone(await ensure_topic(self.bot, self.settings, "announcements"))
        self.bot.send_message.assert_not_awaited()
        self.bot.create_forum_topic.assert_not_awaited()

    async def test_durable_delivery_is_threaded_and_not_repeated(self):
        with patch("app.services.general_topics_service._session_factory", return_value=self.sessions), patch("app.services.notification_service._session_factory", return_value=self.sessions):
            self.assertTrue(await send_general_topic(self.bot, self.settings, "announcements", "Event", delivery_key="event:1"))
            self.assertTrue(await send_general_topic(self.bot, self.settings, "announcements", "Event", delivery_key="event:1"))
        self.bot.send_message.assert_awaited_once_with(-100123, "Event", reply_markup=None, message_thread_id=101)

    async def test_daily_content_only_targets_channel(self):
        with patch("app.services.daily_public_content_service.datetime") as clock, patch("app.services.daily_public_content_service.scheduled_minute", return_value=540), patch("app.services.daily_public_content_service._deliver_once", new=AsyncMock()) as deliver:
            clock.now.return_value = datetime(2026, 10, 9, 21, 55)
            await run_daily_public_content(self.bot, self.settings, self.sessions)
            self.assertEqual(deliver.await_count, 1)
            self.assertEqual(deliver.call_args.kwargs["chat_id"], -100456)

    async def test_legacy_manual_and_scheduled_quotes_are_disabled(self):
        planned = SimpleNamespace(item=SimpleNamespace(content_type="morning_quote", content_id="q1"))
        for manual in (False, True):
            result = await deliver_planned_content(self.bot, self.settings, None, planned, now=datetime.now(), manual=manual)
            self.assertEqual(result.status, "disabled")
        self.bot.send_message.assert_not_awaited()
