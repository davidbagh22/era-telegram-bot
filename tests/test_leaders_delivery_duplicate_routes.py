"""A forum thread shared by multiple Leaders routes must not receive notifications."""
import json
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import AppSetting
from app.services.leaders_topics_service import delivery_topic, topic_id
from app.services.scheduler_service import _send_leaders_task_reminder


class LeadersDeliveryDuplicateRoutesTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def seed(self, chat_id, key, data):
        async with self.sessions() as session:
            session.add(AppSetting(
                key=f"leaders_forum:{chat_id}:{key}", value=json.dumps(data),
            ))
            await session.commit()

    async def test_duplicate_forum_thread_blocks_both_routing_apis(self):
        await self.seed(-1001, "tasks", {"mode": "forum", "thread_id": 11})
        await self.seed(-1001, "pulse", {"mode": "forum", "thread_id": 11})
        async with self.sessions() as session:
            self.assertIsNone(await topic_id(session, -1001, "tasks"))
            self.assertIsNone(await topic_id(session, -1001, "pulse"))
            with self.assertRaisesRegex(ValueError, "одинаковый thread_id"):
                await delivery_topic(session, -1001, "tasks")
            with self.assertRaisesRegex(ValueError, "одинаковый thread_id"):
                await delivery_topic(session, -1001, "pulse")

    async def test_legacy_or_damaged_other_route_cannot_hide_collision(self):
        await self.seed(-1001, "tasks", {"thread_id": 11})
        await self.seed(-1001, "important", {"mode": "plain", "thread_id": 11})
        async with self.sessions() as session:
            self.assertIsNone(await topic_id(session, -1001, "tasks"))
            with self.assertRaisesRegex(ValueError, "одинаковый thread_id"):
                await delivery_topic(session, -1001, "tasks")

    async def test_distinct_routes_and_other_chats_still_deliver(self):
        await self.seed(-1001, "tasks", {"mode": "forum", "thread_id": 11})
        await self.seed(-1001, "pulse", {"mode": "forum", "thread_id": 12})
        await self.seed(-1002, "important", {"mode": "forum", "thread_id": 11})
        async with self.sessions() as session:
            self.assertEqual(await topic_id(session, -1001, "tasks"), 11)
            self.assertEqual(await delivery_topic(session, -1001, "tasks"), 11)
            self.assertEqual(await delivery_topic(session, -1001, "pulse"), 12)

    async def test_uncertain_plain_panel_blocks_reminder_without_writes(self):
        await self.seed(-1001, "tasks", {
            "mode": "plain", "thread_id": None,
            "message_id": 99, "message_state": "uncertain",
        })
        bot = SimpleNamespace(send_message=AsyncMock())
        settings = SimpleNamespace(leaders_chat_id=-1001, general_chat_id=-1002)
        delivery = SimpleNamespace(id=43, chat_id=-1001, message_thread_id=None)
        async with self.sessions() as session:
            before = {
                row.key: row.value for row in
                (await session.scalars(select(AppSetting))).all()
            }
            self.assertFalse(await _send_leaders_task_reminder(
                session, bot, settings, delivery, stage=1,
                deadline=datetime(2026, 10, 27, tzinfo=timezone.utc),
                text="Тестовое напоминание",
            ))
            after = {
                row.key: row.value for row in
                (await session.scalars(select(AppSetting))).all()
            }
            self.assertEqual(before, after)
        bot.send_message.assert_not_awaited()

    async def test_duplicate_thread_prevents_reminder_without_writes(self):
        await self.seed(-1001, "tasks", {"mode": "forum", "thread_id": 11})
        await self.seed(-1001, "important", {"mode": "forum", "thread_id": 11})
        bot = SimpleNamespace(send_message=AsyncMock())
        settings = SimpleNamespace(leaders_chat_id=-1001, general_chat_id=-1002)
        delivery = SimpleNamespace(id=42, chat_id=-1001, message_thread_id=11)
        async with self.sessions() as session:
            before = {
                row.key: row.value for row in
                (await session.scalars(select(AppSetting))).all()
            }
            self.assertFalse(await _send_leaders_task_reminder(
                session, bot, settings, delivery, stage=1,
                deadline=datetime(2026, 10, 27, tzinfo=timezone.utc),
                text="Тестовое напоминание",
            ))
            after = {
                row.key: row.value for row in
                (await session.scalars(select(AppSetting))).all()
            }
            self.assertEqual(before, after)
        bot.send_message.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
