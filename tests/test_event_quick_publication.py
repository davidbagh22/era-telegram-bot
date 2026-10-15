import json
from datetime import date
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter
from aiogram.methods import SendPhoto, SendMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.admin_event_create import EventDraftCreateIn, EventDraftPatch, create_event_draft, publish_event, save_event_draft_step
from app.config import Settings
from app.database.base import Base
from app.database.event_experience import EventExperience
from app.database.models import AppSetting, User
from app.database.system_models import NotificationDelivery
from app.services.event_publication_service import deliver_pending_event_announcements, text_parts


class QuickPublicationTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.settings = Settings(bot_token="1234567890:test-token", bot_username="ERA_1bot", general_chat_id=-100123)
        self.bot = SimpleNamespace(send_photo=AsyncMock(), send_message=AsyncMock())
        async with self.sessions() as session:
            self.admin = User(telegram_id=1, first_name="Admin", phone="+10000001", role="admin")
            session.add(self.admin)
            await session.commit()
        self.factories = [patch(f"app.services.{name}._session_factory", return_value=self.sessions)
                          for name in ("notification_service", "general_topics_service")]
        for factory in self.factories:
            factory.start()

    async def asyncTearDown(self):
        for factory in self.factories:
            factory.stop()
        await self.engine.dispose()

    async def draft(self, text="Встреча ЭРА\nПолный текст анонса"):
        async with self.sessions() as session:
            draft = await create_event_draft(self.admin, session, EventDraftCreateIn(creation_mode="quick"))
            await save_event_draft_step(draft.id, EventDraftPatch(title="Встреча ЭРА", full_description=text,
                short_description="Кратко", location="Дом Москвы", event_date=date(2026, 11, 7)),
                self.admin, session, self.settings, None)
            experience = await session.get(EventExperience, draft.id)
            experience.poster_bytes = b"\x89PNG\r\n\x1a\nposter"
            experience.poster_content_type = "image/png"
            await session.commit()
            return draft.id

    async def topic(self):
        async with self.sessions() as session:
            session.add(AppSetting(key="general_forum:-100123:announcements", value=json.dumps({"thread_id": 101})))
            await session.commit()

    async def publish(self, event_id):
        async with self.sessions() as session:
            return await publish_event(event_id, self.admin, session, self.settings, self.bot)

    async def test_full_text_poster_and_single_publication_survive_repeated_publish(self):
        text = "Встреча ЭРА\n" + "🎉 Текст без обрезки <3\n" * 150
        event_id = await self.draft(text)
        await self.topic()
        first = await self.publish(event_id)
        second = await self.publish(event_id)
        await deliver_pending_event_announcements(self.bot, self.settings, self.sessions)
        self.assertEqual(first.creation_mode, "quick")
        self.assertEqual(first.announcement_status, "sent")
        self.assertEqual(second.announcement_status, "sent")
        self.bot.send_photo.assert_awaited_once()
        call = self.bot.send_photo.await_args
        self.assertEqual(call.kwargs["message_thread_id"], 101)
        self.assertLessEqual(len(call.kwargs["caption"].encode("utf-16-le")) // 2, 1024)
        actual = call.kwargs["caption"] + "".join(item.args[1] for item in self.bot.send_message.await_args_list)
        self.assertEqual(actual, text.strip())
        self.assertIsNotNone(self.bot.send_message.await_args.kwargs["reply_markup"])

    async def test_missing_existing_topic_queues_delivery_and_recovers_after_restart(self):
        event_id = await self.draft()
        published = await self.publish(event_id)
        self.assertEqual(published.announcement_status, "pending")
        self.bot.send_photo.assert_not_awaited()
        await self.topic()
        await deliver_pending_event_announcements(self.bot, self.settings, self.sessions)
        async with self.sessions() as session:
            experience = await session.get(EventExperience, event_id)
            self.assertEqual(experience.announcement_status, "sent")
        self.bot.send_photo.assert_awaited_once()

    async def test_partial_delivery_retries_only_unsent_text(self):
        event_id = await self.draft("Длинный анонс\n" + "текст " * 300)
        await self.topic()
        self.bot.send_message.side_effect = TelegramRetryAfter(method=SendMessage(chat_id=-100123, text="x"), message="retry", retry_after=0)
        published = await self.publish(event_id)
        self.assertEqual(published.announcement_status, "pending")
        self.bot.send_photo.assert_awaited_once()
        self.bot.send_message.side_effect = None
        await deliver_pending_event_announcements(self.bot, self.settings, self.sessions)
        self.bot.send_photo.assert_awaited_once()
        async with self.sessions() as session:
            experience = await session.get(EventExperience, event_id)
            self.assertEqual(experience.announcement_status, "sent")

    async def test_unknown_telegram_outcome_is_not_resent(self):
        event_id = await self.draft()
        await self.topic()
        self.bot.send_photo.side_effect = TelegramNetworkError(method=SendPhoto(chat_id=-100123, photo="x"), message="connection reset")
        published = await self.publish(event_id)
        self.assertEqual(published.announcement_status, "needs_attention")
        await self.publish(event_id)
        await deliver_pending_event_announcements(self.bot, self.settings, self.sessions)
        self.bot.send_photo.assert_awaited_once()
        async with self.sessions() as session:
            delivery = await session.scalar(select(NotificationDelivery))
            self.assertEqual(delivery.status, "uncertain")


def test_text_parts_preserve_unicode_and_telegram_limits():
    text = "🎮" * 6000 + "\nКонец"
    parts = text_parts(text, 1000)
    assert "".join(parts) == text
    assert len(parts[0].encode("utf-16-le")) // 2 <= 1000
    assert all(len(part.encode("utf-16-le")) // 2 <= 4000 for part in parts[1:])
