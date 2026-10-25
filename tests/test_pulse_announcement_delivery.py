import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock

from aiogram.exceptions import TelegramNetworkError
from aiogram.methods import SendMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.database.base import Base
from app.database.models import AppSetting
from app.services.leadership_weekly_service import _send_cycle_announcement
from app.services.notification_service import _session_factory


class PulseAnnouncementDeliveryTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        url = f"sqlite+aiosqlite:///{Path(self.tmp.name) / 'pulse.db'}"
        self.settings = Settings(bot_token="0000000000:CITESTTOKEN", database_url=url, leaders_chat_id=-1001)
        self.engine = create_async_engine(url)
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)
        self.bot = SimpleNamespace(get_me=AsyncMock(return_value=SimpleNamespace(username="era_test_bot")),
            send_message=AsyncMock(return_value=SimpleNamespace(message_id=42)))
        self.cycle = SimpleNamespace(id=1, week_number=43, submitted_count=0, eligible_count=3, announcement_message_id=None)
        self.deadline = datetime(2026, 10, 25, 19, tzinfo=timezone.utc)

    async def asyncTearDown(self):
        await self.engine.dispose()
        _session_factory.cache_clear()
        self.tmp.cleanup()

    async def topic(self, session, data):
        row = await session.scalar(select(AppSetting).where(AppSetting.key == "leaders_forum:-1001:pulse"))
        if row:
            row.value = json.dumps(data)
        else:
            session.add(AppSetting(key="leaders_forum:-1001:pulse", value=json.dumps(data)))
        await session.commit()

    async def test_unknown_or_missing_topic_never_sends_to_the_default_topic(self):
        async with self.factory() as session:
            for value in ({}, {"mode": "broken", "thread_id": 7}, {"mode": False, "thread_id": 7}):
                await self.topic(session, value)
                self.assertFalse(await _send_cycle_announcement(session, self.bot, self.settings, self.cycle, self.deadline))
            self.bot.send_message.assert_not_awaited()
            self.bot.get_me.assert_not_awaited()

    async def test_forum_announcement_replay_restores_id_without_a_duplicate_or_mutating_payload(self):
        async with self.factory() as session:
            await self.topic(session, {"mode": "forum", "thread_id": 7})
            self.assertTrue(await _send_cycle_announcement(session, self.bot, self.settings, self.cycle, self.deadline))
            self.assertEqual(self.cycle.announcement_message_id, 42)
            self.assertEqual(self.bot.send_message.await_args.kwargs["message_thread_id"], 7)
            self.cycle.announcement_message_id = None  # Crash before the business row acknowledgement.
            self.cycle.submitted_count = 2
            self.assertTrue(await _send_cycle_announcement(session, self.bot, self.settings, self.cycle, self.deadline))
            self.assertEqual(self.cycle.announcement_message_id, 42)
            self.bot.send_message.assert_awaited_once()

    async def test_plain_mode_is_explicit_and_uses_no_thread(self):
        async with self.factory() as session:
            await self.topic(session, {"mode": "plain", "thread_id": None})
            self.assertTrue(await _send_cycle_announcement(session, self.bot, self.settings, self.cycle, self.deadline))
            self.assertNotIn("message_thread_id", self.bot.send_message.await_args.kwargs)

    async def test_corrupt_saved_snapshot_never_sends(self):
        async with self.factory() as session:
            await self.topic(session, {"mode": "plain", "thread_id": None})
            session.add(AppSetting(key="pulse-announcement-snapshot:1", value=json.dumps({"chat_id": -1001, "text": "Повреждённый снимок"})))
            await session.commit()
            self.assertFalse(await _send_cycle_announcement(session, self.bot, self.settings, self.cycle, self.deadline))
            self.bot.send_message.assert_not_awaited()

    async def test_uncertain_network_delivery_is_not_retried(self):
        async with self.factory() as session:
            await self.topic(session, {"mode": "forum", "thread_id": 7})
            self.bot.send_message.side_effect = TelegramNetworkError(method=SendMessage(chat_id=-1001, text="test"), message="timeout")
            for _ in range(2):
                self.assertFalse(await _send_cycle_announcement(session, self.bot, self.settings, self.cycle, self.deadline))
            self.bot.send_message.assert_awaited_once()
            self.assertIsNone(self.cycle.announcement_message_id)

    async def test_changed_thread_never_retargets_the_same_cycle_delivery(self):
        async with self.factory() as session:
            await self.topic(session, {"mode": "forum", "thread_id": 7})
            await _send_cycle_announcement(session, self.bot, self.settings, self.cycle, self.deadline)
            self.cycle.announcement_message_id = None
            await self.topic(session, {"mode": "forum", "thread_id": 8})
            self.assertFalse(await _send_cycle_announcement(session, self.bot, self.settings, self.cycle, self.deadline))
            self.bot.send_message.assert_awaited_once()
