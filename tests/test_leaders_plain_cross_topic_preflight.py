"""Plain Leaders chat must reconcile every stored route before any panel I/O."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import AppSetting
from app.services.leaders_topics_service import setup_leaders_topics


class PlainLeadersRoutePreflightTests(unittest.IsolatedAsyncioTestCase):
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
            get_chat=AsyncMock(return_value=SimpleNamespace(type="supergroup", is_forum=False)),
            get_me=AsyncMock(return_value=SimpleNamespace(id=77, username="ERA_1bot")),
            get_chat_member=AsyncMock(return_value=SimpleNamespace(
                status="administrator", can_pin_messages=True,
            )),
            create_forum_topic=AsyncMock(),
            send_message=AsyncMock(return_value=SimpleNamespace(message_id=99)),
            edit_message_text=AsyncMock(),
            pin_chat_message=AsyncMock(),
        )

    async def test_conflicting_secondary_route_blocks_first_panel_without_db_writes(self):
        variants = (
            ("important", '{"mode":"forum","thread_id":7}'),
            ("pulse", "broken-json"),
            ("important", '{"mode":"plain","thread_id":7}'),
            ("pulse", '{"mode":"plain","message_state":"uncertain"}'),
        )
        for key, value in variants:
            with self.subTest(key=key, value=value):
                async with self.sessions() as session:
                    await session.execute(delete(AppSetting))
                    session.add(AppSetting(key=f"leaders_forum:-1001:{key}", value=value))
                    await session.commit()
                bot = self.bot()
                result = await setup_leaders_topics(bot, self.settings, self.sessions)
                self.assertEqual(result, {
                    "status": "topic_needs_review", "chat_id": -1001, "topic": key,
                })
                bot.send_message.assert_not_awaited()
                bot.edit_message_text.assert_not_awaited()
                bot.pin_chat_message.assert_not_awaited()
                bot.create_forum_topic.assert_not_awaited()
                async with self.sessions() as session:
                    rows = (await session.scalars(select(AppSetting).where(
                        AppSetting.key.like("leaders_forum:-1001:%"),
                    ))).all()
                    self.assertEqual([(r.key, r.value) for r in rows], [
                        (f"leaders_forum:-1001:{key}", value),
                    ])

    async def test_conflicting_secondary_route_blocks_existing_panel_edit(self):
        async with self.sessions() as session:
            session.add_all([
                AppSetting(
                    key="leaders_forum:-1001:tasks",
                    value=json.dumps({
                        "mode": "plain", "thread_id": None,
                        "message_id": 55, "message_state": "sent",
                    }),
                ),
                AppSetting(
                    key="leaders_forum:-1001:pulse",
                    value='{"mode":"forum","thread_id":9}',
                ),
            ])
            await session.commit()
        bot = self.bot()
        result = await setup_leaders_topics(bot, self.settings, self.sessions)
        self.assertEqual(result, {
            "status": "topic_needs_review", "chat_id": -1001, "topic": "pulse",
        })
        bot.send_message.assert_not_awaited()
        bot.edit_message_text.assert_not_awaited()
        bot.pin_chat_message.assert_not_awaited()

    async def test_stale_forum_state_on_confirmed_plain_tasks_blocks_edits_and_writes(self):
        original = json.dumps({
            "mode": "plain", "thread_id": None, "thread_state": "creating",
            "message_id": 55, "message_state": "sent",
        })
        async with self.sessions() as session:
            session.add(AppSetting(key="leaders_forum:-1001:tasks", value=original))
            await session.commit()
        bot = self.bot()
        result = await setup_leaders_topics(bot, self.settings, self.sessions)
        self.assertEqual(result, {
            "status": "panel_needs_review", "chat_id": -1001,
        })
        bot.send_message.assert_not_awaited()
        bot.edit_message_text.assert_not_awaited()
        bot.pin_chat_message.assert_not_awaited()
        bot.create_forum_topic.assert_not_awaited()
        async with self.sessions() as session:
            rows = (await session.scalars(select(AppSetting))).all()
            self.assertEqual([(r.key, r.value) for r in rows], [
                ("leaders_forum:-1001:tasks", original),
            ])

    async def test_valid_secondary_plain_routes_allow_single_panel_send(self):
        async with self.sessions() as session:
            session.add_all([
                AppSetting(
                    key=f"leaders_forum:-1001:{key}",
                    value='{"mode":"plain","thread_id":null}',
                )
                for key in ("important", "pulse")
            ])
            await session.commit()
        bot = self.bot()
        self.assertEqual(
            (await setup_leaders_topics(bot, self.settings, self.sessions))["status"],
            "ready_plain",
        )
        self.assertEqual(
            (await setup_leaders_topics(bot, self.settings, self.sessions))["status"],
            "ready_plain",
        )
        self.assertEqual(bot.send_message.await_count, 1)
        self.assertEqual(bot.pin_chat_message.await_count, 1)
        bot.create_forum_topic.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
