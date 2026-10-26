"""A later damaged Leaders forum route must not cause partial Telegram writes."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import AppSetting
from app.services.leaders_topics_service import setup_leaders_topics


class ForumCrossTopicPreflightTests(unittest.IsolatedAsyncioTestCase):
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
            send_message=AsyncMock(return_value=SimpleNamespace(message_id=90)),
            edit_message_text=AsyncMock(),
            pin_chat_message=AsyncMock(),
        )

    async def seed(self, key, data):
        async with self.sessions() as session:
            session.add(AppSetting(
                key=f"leaders_forum:-1001:{key}",
                value=data if isinstance(data, str) else json.dumps(data),
            ))
            await session.commit()

    async def assert_no_writes(self, bot):
        bot.create_forum_topic.assert_not_awaited()
        bot.send_message.assert_not_awaited()
        bot.edit_message_text.assert_not_awaited()
        bot.pin_chat_message.assert_not_awaited()

    async def test_later_corrupt_topic_blocks_existing_tasks_panel_edit(self):
        await self.seed("tasks", {
            "mode": "forum", "thread_id": 11,
            "message_id": 21, "message_state": "sent",
        })
        await self.seed("pulse", '{"mode":"forum","thread_id":12,"message_state":"uncertain"}')
        bot = self.bot()
        result = await setup_leaders_topics(bot, self.settings, self.sessions)
        self.assertEqual(result, {
            "status": "panel_needs_review", "chat_id": -1001, "topic": "pulse",
        })
        await self.assert_no_writes(bot)
        async with self.sessions() as session:
            rows = (await session.scalars(select(AppSetting))).all()
            self.assertEqual(len(rows), 2)
            self.assertEqual(next(r for r in rows if r.key.endswith(":pulse")).value,
                             '{"mode":"forum","thread_id":12,"message_state":"uncertain"}')

    async def test_later_invalid_route_blocks_first_topic_creation(self):
        await self.seed("important", '{"mode":"plain","thread_id":null}')
        bot = self.bot()
        result = await setup_leaders_topics(bot, self.settings, self.sessions)
        self.assertEqual(result, {
            "status": "topic_needs_review", "chat_id": -1001, "topic": "important",
        })
        await self.assert_no_writes(bot)
        async with self.sessions() as session:
            rows = (await session.scalars(select(AppSetting))).all()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].key, "leaders_forum:-1001:important")

    async def test_valid_saved_routes_allow_idempotent_setup(self):
        for key, thread_id in (("tasks", 11), ("pulse", 12), ("important", 13)):
            await self.seed(key, {
                "mode": "forum", "thread_id": thread_id,
                "message_id": thread_id + 100, "message_state": "sent",
                "pinned": True,
            })
        bot = self.bot()
        self.assertEqual(
            (await setup_leaders_topics(bot, self.settings, self.sessions))["status"], "ready",
        )
        self.assertEqual(
            (await setup_leaders_topics(bot, self.settings, self.sessions))["status"], "ready",
        )
        bot.create_forum_topic.assert_not_awaited()
        bot.send_message.assert_not_awaited()
        bot.pin_chat_message.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
