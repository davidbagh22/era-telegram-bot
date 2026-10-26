"""Never republish an untracked legacy Leaders forum panel."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import AppSetting
from app.services.leaders_topics_service import setup_leaders_topics


class LegacyForumPanelRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    def bot(self):
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

    async def test_existing_forum_without_panel_receipt_needs_review_without_writes(self):
        from sqlalchemy import delete
        settings = SimpleNamespace(leaders_chat_id=-1001, general_chat_id=-1002)
        for value in (
            '{"thread_id":7}',
            '{"mode":"forum","thread_id":7,"thread_state":"ready"}',
        ):
            with self.subTest(value=value):
                async with self.factory() as session:
                    await session.execute(delete(AppSetting))
                    session.add(AppSetting(key="leaders_forum:-1001:tasks", value=value))
                    await session.commit()
                bot = self.bot()
                result = await setup_leaders_topics(bot, settings, self.factory)
                self.assertEqual(result, {
                    "status": "panel_needs_review", "chat_id": -1001, "topic": "tasks",
                })
                bot.create_forum_topic.assert_not_awaited()
                bot.send_message.assert_not_awaited()
                bot.edit_message_text.assert_not_awaited()
                bot.pin_chat_message.assert_not_awaited()
                async with self.factory() as session:
                    row = await session.scalar(select(AppSetting).where(
                        AppSetting.key == "leaders_forum:-1001:tasks",
                    ))
                    self.assertEqual(row.value, value)
                    self.assertIsNone(await session.scalar(select(AppSetting).where(
                        AppSetting.key == "leaders_forum:-1001:pulse",
                    )))

    async def test_new_forum_still_creates_and_sends_each_panel_once(self):
        settings = SimpleNamespace(leaders_chat_id=-1001, general_chat_id=-1002)
        bot = self.bot()
        bot.create_forum_topic.side_effect = [
            SimpleNamespace(message_thread_id=n) for n in (11, 12, 13)
        ]
        bot.send_message.return_value = SimpleNamespace(message_id=99)
        result = await setup_leaders_topics(bot, settings, self.factory)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(bot.create_forum_topic.await_count, 3)
        self.assertEqual(bot.send_message.await_count, 3)
        again = await setup_leaders_topics(bot, settings, self.factory)
        self.assertEqual(again["status"], "ready")
        self.assertEqual(bot.send_message.await_count, 3)


if __name__ == "__main__":
    unittest.main()
