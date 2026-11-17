"""Leaders panel pin must treat already-pinned as durable success."""
from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram.exceptions import TelegramBadRequest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import AppSetting
from app.services.leaders_topics_service import setup_leaders_topics


class LeadersPinAlreadyPinnedTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.settings = SimpleNamespace(leaders_chat_id=-1001, general_chat_id=-1002)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def test_already_pinned_marks_receipt_and_stays_ready(self) -> None:
        bot = SimpleNamespace(
            get_chat=AsyncMock(return_value=SimpleNamespace(type="supergroup", is_forum=False)),
            get_me=AsyncMock(return_value=SimpleNamespace(id=77, username="ERA_1bot")),
            get_chat_member=AsyncMock(
                return_value=SimpleNamespace(status="administrator", can_pin_messages=True)
            ),
            send_message=AsyncMock(return_value=SimpleNamespace(message_id=91)),
            edit_message_text=AsyncMock(),
            pin_chat_message=AsyncMock(
                side_effect=TelegramBadRequest(
                    method=SimpleNamespace(),
                    message="Bad Request: message is already pinned",
                )
            ),
        )

        first = await setup_leaders_topics(bot, self.settings, self.sessions)
        second = await setup_leaders_topics(bot, self.settings, self.sessions)

        self.assertEqual(first["status"], "ready_plain")
        self.assertEqual(second["status"], "ready_plain")
        self.assertEqual(bot.pin_chat_message.await_count, 1)

        async with self.sessions() as session:
            row = await session.scalar(
                select(AppSetting).where(AppSetting.key == "leaders_forum:-1001:tasks")
            )
            data = json.loads(row.value)
        self.assertTrue(data.get("pinned"))
        self.assertEqual(data.get("message_id"), 91)


if __name__ == "__main__":
    unittest.main()
