"""Already-pinned must confirm durable pins across registration/games/FAQ."""
from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import PinChatMessage
from aiogram.types import Chat, Message, User as TelegramUser
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.services.chat_access_service import ensure_general_registration_pin
from app.services.games_launch_service import refresh_games_pin
from app.utils.telegram_pin import telegram_already_pinned


class TelegramAlreadyPinnedHelperTests(unittest.TestCase):
    def test_human_and_machine_codes(self) -> None:
        self.assertTrue(telegram_already_pinned(Exception("Bad Request: message is already pinned")))
        self.assertTrue(telegram_already_pinned(Exception("MESSAGE_ALREADY_PINNED")))
        self.assertFalse(telegram_already_pinned(Exception("CHAT_NOT_MODIFIED")))


class RegistrationPinAlreadyPinnedTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def test_already_pinned_still_records_sent(self) -> None:
        bot = SimpleNamespace(
            get_me=AsyncMock(return_value=SimpleNamespace(id=77)),
            get_chat=AsyncMock(return_value=SimpleNamespace(pinned_message=None)),
            send_message=AsyncMock(return_value=SimpleNamespace(message_id=42)),
            pin_chat_message=AsyncMock(
                side_effect=TelegramBadRequest(
                    method=PinChatMessage(chat_id=-1001, message_id=42),
                    message="Bad Request: message is already pinned",
                )
            ),
        )
        ok = await ensure_general_registration_pin(bot, -1001, self.sessions)
        self.assertTrue(ok)
        bot.pin_chat_message.assert_awaited_once()


class GamesPinAlreadyPinnedTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def test_already_pinned_confirms_menu(self) -> None:
        me = TelegramUser(id=123, first_name="ERA", is_bot=True)
        pinned = Message(
            message_id=500,
            date=datetime.now(timezone.utc),
            chat=Chat(id=-100123456, type="supergroup"),
            message_thread_id=99,
            from_user=me,
            text="🎮 ЭРА | Интерактив\nменю",
        )
        settings = SimpleNamespace(general_chat_id=-100123456, bot_username="ERA_1bot")
        bot = SimpleNamespace(
            get_me=AsyncMock(return_value=me),
            get_chat=AsyncMock(return_value=SimpleNamespace(pinned_message=pinned)),
            edit_message_text=AsyncMock(return_value=True),
            pin_chat_message=AsyncMock(
                side_effect=TelegramBadRequest(
                    method=PinChatMessage(chat_id=-100123456, message_id=500),
                    message="MESSAGE_ALREADY_PINNED",
                )
            ),
            send_message=AsyncMock(),
        )
        self.assertTrue(await refresh_games_pin(bot, settings, self.sessions, 99))
        bot.send_message.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
