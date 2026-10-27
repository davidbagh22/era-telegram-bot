"""A confirmed plain Leaders panel should not be edited every scheduler pass."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import AppSetting
from app.services.leaders_topics_service import setup_leaders_topics


class PlainPanelEditDedupTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.settings = SimpleNamespace(leaders_chat_id=-1001, general_chat_id=-1002)
        self.bot = SimpleNamespace(
            get_chat=AsyncMock(return_value=SimpleNamespace(type="supergroup", is_forum=False)),
            get_me=AsyncMock(return_value=SimpleNamespace(id=77, username="ERA_1bot")),
            get_chat_member=AsyncMock(return_value=SimpleNamespace(
                status="administrator", can_pin_messages=True,
            )),
            send_message=AsyncMock(return_value=SimpleNamespace(message_id=91)),
            edit_message_text=AsyncMock(),
            pin_chat_message=AsyncMock(),
        )

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def saved(self):
        async with self.sessions() as session:
            row = await session.scalar(select(AppSetting).where(
                AppSetting.key == "leaders_forum:-1001:tasks"
            ))
            return json.loads(row.value)

    async def test_new_panel_sent_once_and_never_edited_when_unchanged(self):
        for _ in range(3):
            result = await setup_leaders_topics(self.bot, self.settings, self.sessions)
            self.assertEqual(result["status"], "ready_plain")
        self.bot.send_message.assert_awaited_once()
        self.bot.edit_message_text.assert_not_awaited()
        self.bot.pin_chat_message.assert_awaited_once()
        data = await self.saved()
        self.assertEqual(data["message_id"], 91)
        self.assertEqual(data["message_state"], "sent")
        self.assertEqual(data["panel"]["text"].splitlines()[0], "⚙️ РАБОЧИЙ ЦЕНТР ЭРА")

    async def test_legacy_confirmed_panel_is_reconciled_only_once(self):
        async with self.sessions() as session:
            session.add(AppSetting(
                key="leaders_forum:-1001:tasks",
                value=json.dumps({
                    "mode": "plain", "thread_id": None, "message_id": 55,
                    "message_state": "sent", "pinned": True,
                }),
            ))
            await session.commit()
        for _ in range(3):
            self.assertEqual(
                (await setup_leaders_topics(self.bot, self.settings, self.sessions))["status"],
                "ready_plain",
            )
        self.bot.send_message.assert_not_awaited()
        self.bot.edit_message_text.assert_awaited_once()
        self.bot.pin_chat_message.assert_not_awaited()
        self.assertIn("panel", await self.saved())

    async def test_changed_panel_is_edited_once_and_snapshot_updated(self):
        await setup_leaders_topics(self.bot, self.settings, self.sessions)
        with patch("app.services.leaders_topics_service.panel", new_callable=AsyncMock) as render:
            render.return_value = ("Обновлённый центр", None)
            await setup_leaders_topics(self.bot, self.settings, self.sessions)
            await setup_leaders_topics(self.bot, self.settings, self.sessions)
        self.bot.send_message.assert_awaited_once()
        self.bot.edit_message_text.assert_awaited_once()
        self.assertEqual((await self.saved())["panel"], {
            "text": "Обновлённый центр", "keyboard": None,
        })


if __name__ == "__main__":
    unittest.main()
