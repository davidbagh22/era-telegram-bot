"""Conflicting saved forum destinations must never trigger Telegram writes."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import AppSetting
from app.services.leaders_topics_service import setup_leaders_topics


class ForumDuplicateRouteTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.settings = SimpleNamespace(leaders_chat_id=-1001, general_chat_id=-1002)

    async def asyncTearDown(self):
        await self.engine.dispose()

    @staticmethod
    def bot():
        return SimpleNamespace(
            get_chat=AsyncMock(return_value=SimpleNamespace(type="supergroup", is_forum=True)),
            get_me=AsyncMock(return_value=SimpleNamespace(id=77, username="ERA_1bot")),
            get_chat_member=AsyncMock(return_value=SimpleNamespace(
                status="administrator", can_manage_topics=True, can_pin_messages=True,
            )),
            create_forum_topic=AsyncMock(),
            send_message=AsyncMock(),
            edit_message_text=AsyncMock(),
            pin_chat_message=AsyncMock(),
        )

    async def seed(self, key, thread_id, message_id):
        value = json.dumps({
            "mode": "forum", "thread_id": thread_id, "thread_state": "ready",
            "message_id": message_id, "message_state": "sent", "pinned": True,
        })
        async with self.sessions() as session:
            session.add(AppSetting(key=f"leaders_forum:-1001:{key}", value=value))
            await session.commit()

    async def assert_unchanged(self, bot, original):
        bot.create_forum_topic.assert_not_awaited()
        bot.send_message.assert_not_awaited()
        bot.edit_message_text.assert_not_awaited()
        bot.pin_chat_message.assert_not_awaited()
        async with self.sessions() as session:
            rows = (await session.scalars(select(AppSetting))).all()
            self.assertEqual({r.key: r.value for r in rows}, original)

    async def snapshot(self):
        async with self.sessions() as session:
            rows = (await session.scalars(select(AppSetting))).all()
            return {r.key: r.value for r in rows}

    async def test_duplicate_thread_ids_block_all_writes(self):
        await self.seed("tasks", 11, 101)
        await self.seed("pulse", 11, 102)
        original = await self.snapshot()
        bot = self.bot()
        self.assertEqual(await setup_leaders_topics(bot, self.settings, self.sessions), {
            "status": "topic_needs_review", "chat_id": -1001, "topic": "pulse",
        })
        await self.assert_unchanged(bot, original)

    async def test_duplicate_panel_message_ids_block_all_writes(self):
        await self.seed("tasks", 11, 101)
        await self.seed("important", 13, 101)
        original = await self.snapshot()
        bot = self.bot()
        self.assertEqual(await setup_leaders_topics(bot, self.settings, self.sessions), {
            "status": "panel_needs_review", "chat_id": -1001, "topic": "important",
        })
        await self.assert_unchanged(bot, original)

    async def test_duplicate_later_route_blocks_creating_missing_pulse(self):
        await self.seed("tasks", 11, 101)
        await self.seed("important", 11, 103)
        original = await self.snapshot()
        bot = self.bot()
        self.assertEqual(await setup_leaders_topics(bot, self.settings, self.sessions), {
            "status": "topic_needs_review", "chat_id": -1001, "topic": "important",
        })
        await self.assert_unchanged(bot, original)


if __name__ == "__main__":
    unittest.main()
