from __future__ import annotations

import unittest
from types import SimpleNamespace

from aiogram.exceptions import TelegramNetworkError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.database.base import Base
from app.database.models import AuditLog
from app.services.chat_faq_service import FAQ_PINNED_MESSAGE, ChatFaqError, publish_faq_message


class FakeBot:
    def __init__(self, *, fail_send: bool = False, fail_pin: bool = False) -> None:
        self.fail_send = fail_send
        self.fail_pin = fail_pin
        self.sent: list[tuple[int, str, str | None]] = []
        self.edited: list[tuple[int, int, str, str | None]] = []
        self.pinned: list[tuple[int, int]] = []
        self.last_markup = None

    async def get_me(self):
        return SimpleNamespace(username="EraTestBot")

    async def send_message(self, chat_id: int, text: str, reply_markup=None, parse_mode=None):
        if self.fail_send:
            raise TelegramNetworkError(method="sendMessage", message="network down")
        self.sent.append((chat_id, text, parse_mode))
        self.last_markup = reply_markup
        return SimpleNamespace(message_id=555)

    async def edit_message_text(
        self,
        text: str,
        *,
        chat_id: int,
        message_id: int,
        reply_markup=None,
        parse_mode=None,
    ):
        self.edited.append((chat_id, message_id, text, parse_mode))
        self.last_markup = reply_markup
        return SimpleNamespace(message_id=message_id)

    async def pin_chat_message(self, chat_id: int, message_id: int, disable_notification: bool = True):
        if self.fail_pin:
            raise TelegramNetworkError(method="pinChatMessage", message="not admin")
        self.pinned.append((chat_id, message_id))


class ChatFaqServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def test_publish_sends_html_and_pins(self) -> None:
        async with self.session_factory() as session:
            bot = FakeBot()
            settings = Settings(bot_token="1234567890:test-token", general_chat_id=-100555)
            result = await publish_faq_message(bot, settings, session, actor_id=1)
            self.assertTrue(result.pinned)
            self.assertEqual(result.message_id, 555)
            self.assertEqual(bot.sent, [(-100555, FAQ_PINNED_MESSAGE, "HTML")])
            self.assertEqual(bot.pinned, [(-100555, 555)])
            audit_rows = (await session.scalars(select(AuditLog))).all()
            self.assertEqual(len(audit_rows), 1)
            self.assertEqual(audit_rows[0].action, "chat.faq_published")
            self.assertEqual(audit_rows[0].entity_id, 555)
            self.assertEqual(audit_rows[0].new_value, {"chat": "general", "pinned": True})

    async def test_publish_uses_links_that_open_private_bot_chat(self) -> None:
        async with self.session_factory() as session:
            bot = FakeBot()
            settings = Settings(bot_token="1234567890:test-token", general_chat_id=-100555)
            await publish_faq_message(bot, settings, session, actor_id=1)

            rows = bot.last_markup.inline_keyboard
            self.assertEqual(rows[0][0].callback_data, "faq:events")
            self.assertEqual(rows[0][1].callback_data, "faq:profile")

            topic_rows = rows[1:]
            urls = [row[0].url for row in topic_rows]
            self.assertTrue(all(url and url.startswith("https://t.me/EraTestBot?start=faq_") for url in urls))
            self.assertTrue(all(row[0].callback_data is None for row in topic_rows))

    async def test_second_publish_reuses_recorded_message_instead_of_spamming(self) -> None:
        async with self.session_factory() as session:
            bot = FakeBot()
            settings = Settings(bot_token="1234567890:test-token", general_chat_id=-100555)
            first = await publish_faq_message(bot, settings, session, actor_id=1)
            second = await publish_faq_message(bot, settings, session, actor_id=None)
            self.assertEqual(first.message_id, second.message_id)
            self.assertEqual(len(bot.sent), 1)
            self.assertEqual(bot.edited, [(-100555, 555, FAQ_PINNED_MESSAGE, "HTML")])
            self.assertEqual(bot.pinned, [(-100555, 555), (-100555, 555)])

    async def test_publish_rejects_unbound_chat(self) -> None:
        async with self.session_factory() as session:
            bot = FakeBot()
            settings = Settings(bot_token="1234567890:test-token")
            with self.assertRaises(ChatFaqError) as ctx:
                await publish_faq_message(bot, settings, session, actor_id=1)
            self.assertEqual(ctx.exception.code, "chat_not_bound")
            self.assertEqual(bot.sent, [])

    async def test_publish_survives_pin_failure(self) -> None:
        async with self.session_factory() as session:
            bot = FakeBot(fail_pin=True)
            settings = Settings(bot_token="1234567890:test-token", general_chat_id=-100555)
            result = await publish_faq_message(bot, settings, session, actor_id=1)
            self.assertFalse(result.pinned)
            self.assertEqual(len(bot.sent), 1)
            audit_rows = (await session.scalars(select(AuditLog))).all()
            self.assertEqual(audit_rows[0].entity_id, 555)
            self.assertEqual(audit_rows[0].new_value, {"chat": "general", "pinned": False})

    async def test_publish_raises_when_send_fails(self) -> None:
        async with self.session_factory() as session:
            bot = FakeBot(fail_send=True)
            settings = Settings(bot_token="1234567890:test-token", general_chat_id=-100555)
            with self.assertRaises(ChatFaqError) as ctx:
                await publish_faq_message(bot, settings, session, actor_id=1)
            self.assertEqual(ctx.exception.code, "send_failed")
            audit_rows = (await session.scalars(select(AuditLog))).all()
            self.assertEqual(len(audit_rows), 0)


if __name__ == "__main__":
    unittest.main()
