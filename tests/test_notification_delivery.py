from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.database.base import Base
from app.database.system_models import NotificationDelivery
from app.services.notification_service import _session_factory, safe_send_once


class FakeBot:
    def __init__(self, failure: Exception | None = None) -> None:
        self.failure = failure
        self.calls: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str, **kwargs):
        self.calls.append((chat_id, text))
        if self.failure is not None:
            raise self.failure
        return object()


class DurableNotificationDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        db_path = Path(self.tmp.name) / "notification-test.db"
        self.database_url = f"sqlite+aiosqlite:///{db_path}"
        self.settings = Settings(
            bot_token="1234567890:test-token",
            database_url=self.database_url,
        )
        self.engine = create_async_engine(self.database_url)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()
        _session_factory.cache_clear()
        self.tmp.cleanup()

    async def test_same_delivery_key_sends_exactly_once(self) -> None:
        bot = FakeBot()
        first = await safe_send_once(
            bot,
            self.settings,
            900001,
            "Важное уведомление ЭРА",
            delivery_key="test:once:900001",
            notification_type="test",
        )
        second = await safe_send_once(
            bot,
            self.settings,
            900001,
            "Важное уведомление ЭРА",
            delivery_key="test:once:900001",
            notification_type="test",
        )

        self.assertTrue(first.sent)
        self.assertFalse(first.duplicate)
        self.assertTrue(second.sent)
        self.assertTrue(second.duplicate)
        self.assertEqual(second.status, "sent")
        self.assertEqual(len(bot.calls), 1)

        async with self.session_factory() as session:
            row = await session.scalar(
                select(NotificationDelivery).where(
                    NotificationDelivery.delivery_key == "test:once:900001"
                )
            )
        self.assertIsNotNone(row)
        self.assertEqual(row.status, "sent")
        self.assertEqual(row.attempt_count, 1)
        self.assertIsNotNone(row.sent_at)

    async def test_delivery_key_cannot_be_reused_for_different_payload(self) -> None:
        bot = FakeBot()
        await safe_send_once(
            bot,
            self.settings,
            900001,
            "Первый текст",
            delivery_key="test:conflict:900001",
            notification_type="test",
        )
        conflict = await safe_send_once(
            bot,
            self.settings,
            900001,
            "Другой текст",
            delivery_key="test:conflict:900001",
            notification_type="test",
        )

        self.assertFalse(conflict.sent)
        self.assertTrue(conflict.duplicate)
        self.assertEqual(conflict.status, "conflict")
        self.assertEqual(conflict.error_code, "delivery_key_conflict")
        self.assertEqual(len(bot.calls), 1)

    async def test_blocked_recipient_is_terminal_and_not_retried_next_run(self) -> None:
        method = SendMessage(chat_id=900001, text="Тест")
        bot = FakeBot(
            TelegramForbiddenError(
                method=method,
                message="Forbidden: bot was blocked by the user",
            )
        )
        first = await safe_send_once(
            bot,
            self.settings,
            900001,
            "Тест",
            delivery_key="test:blocked:900001",
            notification_type="test",
            max_attempts=3,
        )
        second = await safe_send_once(
            bot,
            self.settings,
            900001,
            "Тест",
            delivery_key="test:blocked:900001",
            notification_type="test",
            max_attempts=3,
        )

        self.assertEqual(first.status, "blocked")
        self.assertFalse(first.sent)
        self.assertTrue(second.duplicate)
        self.assertEqual(second.status, "blocked")
        self.assertEqual(len(bot.calls), 1)

    def test_ledger_schema_does_not_store_message_or_profile_payload(self) -> None:
        columns = set(NotificationDelivery.__table__.columns.keys())
        self.assertIn("payload_hash", columns)
        for forbidden in (
            "text",
            "body",
            "payload",
            "reply_markup",
            "phone",
            "email",
            "vector",
            "personal_notes",
        ):
            self.assertNotIn(forbidden, columns)


if __name__ == "__main__":
    unittest.main()
