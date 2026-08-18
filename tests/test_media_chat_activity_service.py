from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.services.media_chat_activity_service import (
    chat_activity_summary,
    is_human_content_message,
    record_media_chat_message,
)


def _message(**overrides) -> SimpleNamespace:
    defaults = dict(
        from_user=SimpleNamespace(id=1, is_bot=False),
        text=None,
        caption=None,
        photo=None,
        video=None,
        document=None,
        voice=None,
        video_note=None,
        audio=None,
        sticker=None,
        new_chat_members=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class IsHumanContentMessageTests(unittest.TestCase):
    """DELTA ToR §39: text/photo/video/document/voice/reply count; bot
    messages and service events (join/leave/...) don't."""

    def test_text_message_counts(self) -> None:
        self.assertTrue(is_human_content_message(_message(text="hi")))

    def test_photo_video_document_voice_count(self) -> None:
        for field in ("photo", "video", "document", "voice"):
            with self.subTest(field=field):
                self.assertTrue(is_human_content_message(_message(**{field: object()})))

    def test_reply_with_caption_only_counts(self) -> None:
        self.assertTrue(is_human_content_message(_message(caption="see above")))

    def test_bot_message_does_not_count(self) -> None:
        msg = _message(text="automated", from_user=SimpleNamespace(id=99, is_bot=True))
        self.assertFalse(is_human_content_message(msg))

    def test_no_from_user_does_not_count(self) -> None:
        self.assertFalse(is_human_content_message(_message(text="anon", from_user=None)))

    def test_pure_service_event_does_not_count(self) -> None:
        # A join event carries new_chat_members but no text/media -- must
        # not count as a contribution even though from_user is set.
        msg = _message(new_chat_members=[SimpleNamespace(id=2, is_bot=False)])
        self.assertFalse(is_human_content_message(msg))


class ChatActivitySummaryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def test_record_message_increments_count_and_dedups_authors(self) -> None:
        async with self.session_factory() as session:
            await record_media_chat_message(session, chat_id=1, telegram_user_id=10)
            await record_media_chat_message(session, chat_id=1, telegram_user_id=10)
            await record_media_chat_message(session, chat_id=1, telegram_user_id=20)

            summary = await chat_activity_summary(session, 1)
            self.assertEqual(summary.messages_7d, 3)
            self.assertEqual(summary.active_authors_7d, 2)

    async def test_summary_excludes_messages_outside_window_and_other_chats(self) -> None:
        async with self.session_factory() as session:
            now = datetime.now(timezone.utc)
            await record_media_chat_message(session, chat_id=1, telegram_user_id=1, when=now - timedelta(days=1))
            await record_media_chat_message(session, chat_id=1, telegram_user_id=2, when=now - timedelta(days=20))
            await record_media_chat_message(session, chat_id=1, telegram_user_id=3, when=now - timedelta(days=45))
            await record_media_chat_message(session, chat_id=2, telegram_user_id=4, when=now)

            summary = await chat_activity_summary(session, 1, now=now)
            self.assertEqual(summary.messages_7d, 1)
            self.assertEqual(summary.messages_30d, 2)

    async def test_trend_compares_to_previous_30_day_window(self) -> None:
        async with self.session_factory() as session:
            now = datetime.now(timezone.utc)
            # Previous 30d window: 10 messages.
            for i in range(10):
                await record_media_chat_message(session, chat_id=1, telegram_user_id=i, when=now - timedelta(days=40))
            # Current 30d window: 15 messages -- +50%.
            for i in range(15):
                await record_media_chat_message(session, chat_id=1, telegram_user_id=100 + i, when=now - timedelta(days=5))

            summary = await chat_activity_summary(session, 1, now=now)
            self.assertAlmostEqual(summary.trend_vs_previous_period, 0.5)

    async def test_trend_is_none_without_a_previous_period_baseline(self) -> None:
        async with self.session_factory() as session:
            await record_media_chat_message(session, chat_id=1, telegram_user_id=1)
            summary = await chat_activity_summary(session, 1)
            self.assertIsNone(summary.trend_vs_previous_period)


if __name__ == "__main__":
    unittest.main()
