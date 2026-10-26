"""Regression coverage for the one-time ReplyKeyboardRemove migration.

Scenario from the request: an existing user whose Telegram client still has
the bot's old persistent ReplyKeyboardMarkup main menu cached (sent weeks
ago, before that keyboard builder was removed) sends /start (or any other
message) -> gets ReplyKeyboardRemove() exactly once -> the flag flips so
later interactions never repeat it.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram.exceptions import TelegramAPIError
from aiogram.types import ReplyKeyboardRemove

from app.middlewares.legacy_keyboard_cleanup import LegacyKeyboardCleanupMiddleware


class FakeBot:
    def __init__(self, *, raise_on_send: bool = False) -> None:
        self.sent: list[tuple[int, str, dict]] = []
        self._raise_on_send = raise_on_send

    async def send_message(self, chat_id, text, **kwargs):
        if self._raise_on_send:
            raise TelegramAPIError(method=SimpleNamespace(), message="blocked")
        self.sent.append((chat_id, text, kwargs))


def _user(*, legacy_removed: bool) -> SimpleNamespace:
    return SimpleNamespace(telegram_id=900001, legacy_reply_keyboard_removed=legacy_removed)


class LegacyKeyboardCleanupMiddlewareTests(unittest.IsolatedAsyncioTestCase):
    async def test_unmigrated_user_gets_reply_keyboard_remove_once(self) -> None:
        user = _user(legacy_removed=False)
        bot = FakeBot()
        handler_calls = []

        async def handler(event, data):
            handler_calls.append(event)
            return "handled"

        result = await LegacyKeyboardCleanupMiddleware()(
            handler,
            event=object(),
            data={"user": user, "event_chat": SimpleNamespace(id=42, type="private"), "bot": bot},
        )

        self.assertEqual(result, "handled")
        self.assertEqual(len(handler_calls), 1)
        self.assertEqual(len(bot.sent), 1)
        chat_id, text, kwargs = bot.sent[0]
        self.assertEqual(chat_id, 42)
        self.assertTrue(text)  # Telegram requires non-empty text
        self.assertIsInstance(kwargs["reply_markup"], ReplyKeyboardRemove)
        # The migration flag flips on the same ORM-style object the caller
        # already holds — DatabaseAuthMiddleware's own session.commit()
        # (which runs after this middleware returns) is what persists it;
        # nothing extra is needed here.
        self.assertTrue(user.legacy_reply_keyboard_removed)

    async def test_already_migrated_user_is_not_messaged_again(self) -> None:
        user = _user(legacy_removed=True)
        bot = FakeBot()

        async def handler(event, data):
            return None

        await LegacyKeyboardCleanupMiddleware()(
            handler,
            event=object(),
            data={"user": user, "event_chat": SimpleNamespace(id=42, type="private"), "bot": bot},
        )

        self.assertEqual(bot.sent, [])
        self.assertTrue(user.legacy_reply_keyboard_removed)

    async def test_repeated_interactions_after_cleanup_never_spam(self) -> None:
        # Same user, same middleware instance, three consecutive Updates —
        # exactly the "не спамить" requirement: at most one
        # ReplyKeyboardRemove ever, regardless of how many messages follow.
        user = _user(legacy_removed=False)
        bot = FakeBot()
        middleware = LegacyKeyboardCleanupMiddleware()

        async def handler(event, data):
            return None

        for _ in range(3):
            data = {"user": user, "event_chat": SimpleNamespace(id=42, type="private"), "bot": bot}
            await middleware(handler, event=object(), data=data)

        self.assertEqual(len(bot.sent), 1)

    async def test_group_chats_are_never_targeted(self) -> None:
        user = _user(legacy_removed=False)
        bot = FakeBot()

        async def handler(event, data):
            return None

        await LegacyKeyboardCleanupMiddleware()(
            handler,
            event=object(),
            data={"user": user, "event_chat": SimpleNamespace(id=-100, type="group"), "bot": bot},
        )

        self.assertEqual(bot.sent, [])
        # Flag deliberately untouched — this user's private chat may still
        # need the real cleanup later.
        self.assertFalse(user.legacy_reply_keyboard_removed)

    async def test_no_authenticated_user_is_a_noop(self) -> None:
        bot = FakeBot()

        async def handler(event, data):
            return "ok"

        result = await LegacyKeyboardCleanupMiddleware()(
            handler,
            event=object(),
            data={"user": None, "event_chat": SimpleNamespace(id=42, type="private"), "bot": bot},
        )

        self.assertEqual(result, "ok")
        self.assertEqual(bot.sent, [])

    async def test_delivery_failure_does_not_mark_the_flag(self) -> None:
        # Best-effort: a blocked bot / deactivated chat / transient API
        # error must not be recorded as "cleaned up" — the user should get
        # a real retry on their next Update instead of being silently
        # skipped forever.
        user = _user(legacy_removed=False)
        bot = FakeBot(raise_on_send=True)
        handler_calls = []

        async def handler(event, data):
            handler_calls.append(event)
            return "handled anyway"

        result = await LegacyKeyboardCleanupMiddleware()(
            handler,
            event=object(),
            data={"user": user, "event_chat": SimpleNamespace(id=42, type="private"), "bot": bot},
        )

        self.assertEqual(result, "handled anyway")
        self.assertEqual(len(handler_calls), 1)
        self.assertFalse(user.legacy_reply_keyboard_removed)


if __name__ == "__main__":
    unittest.main()


class CurrentPersistentKeyboardMigrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_approved_admin_receives_statistics_keyboard_instead_of_remove(self):
        from aiogram.types import ReplyKeyboardMarkup
        from app.config import Settings
        from app.utils.constants import ApplicationStatus, Role
        user = SimpleNamespace(telegram_id=900001, legacy_reply_keyboard_removed=False,
                               application_status=ApplicationStatus.APPROVED, role=Role.ADMIN,
                               is_blocked=False, is_archived=False)
        bot = FakeBot()
        handler = AsyncMock()
        settings = Settings(bot_token="1234567890:test-token")
        data = {"user": user, "event_chat": SimpleNamespace(id=42, type="private"), "bot": bot, "settings": settings}
        middleware = LegacyKeyboardCleanupMiddleware()
        await middleware(handler, object(), data)
        await middleware(handler, object(), data)
        assert len(bot.sent) == 1
        markup = bot.sent[0][2]["reply_markup"]
        assert isinstance(markup, ReplyKeyboardMarkup)
        assert markup.is_persistent and markup.one_time_keyboard is False
        assert "📊 Статистика" in {button.text for row in markup.keyboard for button in row}
        assert user.legacy_reply_keyboard_removed


class VersionedPrivateMenuTests(unittest.IsolatedAsyncioTestCase):
    async def test_old_legacy_flag_does_not_block_current_menu_and_next_update_is_silent(self):
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
        from app.database.base import Base
        from app.database.models import AppSetting
        from app.config import Settings
        from app.utils.constants import ApplicationStatus, Role
        engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            user = SimpleNamespace(telegram_id=900001, legacy_reply_keyboard_removed=True,
                                   application_status=ApplicationStatus.APPROVED, role=Role.ADMIN,
                                   is_blocked=False, is_archived=False)
            bot = FakeBot()
            middleware = LegacyKeyboardCleanupMiddleware()
            async with sessions() as session:
                session.add(AppSetting(key='private-menu:900001', value={
                    'version': '2026-10-18-clean', 'admin': True, 'leaders': True,
                }))
                await session.commit()
                data = {'user': user, 'event_chat': SimpleNamespace(id=42, type='private'), 'bot': bot,
                        'settings': Settings(bot_token='1234567890:test-token', miniapp_auth_secret='test-secret',
                                             miniapp_url='https://era.example/app/'), 'session': session}
                for _ in range(3):
                    await middleware(AsyncMock(), object(), data)
                    await session.commit()
            assert len(bot.sent) == 1
            labels = {b.text for row in bot.sent[0][2]['reply_markup'].keyboard for b in row}
            assert '📊 Статистика' in labels and '💬 Связь' in labels
            assert '❓ Вопросы и связь' not in labels
            assert '🔥 Открыть ЭРА' in labels
            assert all(b.web_app is None for row in bot.sent[0][2]['reply_markup'].keyboard for b in row)
        finally:
            await engine.dispose()
