"""Published event share copy uses persisted links; it never posts to Telegram."""
from datetime import date, time
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock

from fastapi import HTTPException

from app.api.v1.admin_event_operations import read_event_share_text
from app.database.event_experience import EventExperience
from app.database.models import Event
from app.utils.constants import EventStatus


class EventShareTextTests(IsolatedAsyncioTestCase):
    def make_context(self, status=EventStatus.REGISTRATION_OPEN, topic="https://t.me/c/123/900"):
        event = SimpleNamespace(
            id=42, title="Литература Победы", description="Диалог",
            event_date=date(2026, 11, 23), event_time=time(13),
            location="Дом Москвы", status=status,
        )
        experience = SimpleNamespace(
            full_description="Литература Победы\n\nОбщая программа",
            chat_url=topic, end_time=None,
        )
        session = SimpleNamespace(get=AsyncMock(side_effect=lambda model, ident:
            event if model is Event else experience if model is EventExperience else None))
        settings = SimpleNamespace(bot_username="ERA_1bot", general_chat_url="https://t.me/+era")
        return session, settings

    async def test_public_share_is_copyable_with_actual_links(self):
        session, settings = self.make_context()
        reply = await read_event_share_text(
            42, _admin=SimpleNamespace(), session=session, settings=settings,
        )
        self.assertEqual(reply.text.count("Литература Победы"), 1)
        self.assertIn("23.11.2026 · 13:00", reply.text)
        self.assertIn("https://t.me/c/123/900", reply.text)
        self.assertIn("https://t.me/+era", reply.text)
        self.assertIn("startapp=event_42", reply.text)

    async def test_external_event_share_uses_organizer_signup(self):
        session, settings = self.make_context()
        experience = await session.get(EventExperience, 42)
        experience.registration_required = False
        experience.contact = "https://t.me/+quri_BnuHaxjZTVi"
        reply = await read_event_share_text(
            42, _admin=SimpleNamespace(), session=session, settings=settings,
        )
        self.assertIn("Зарегистрироваться: https://t.me/+quri_BnuHaxjZTVi", reply.text)
        self.assertNotIn("startapp=event_42", reply.text)

    async def test_missing_topic_is_not_invented(self):
        session, settings = self.make_context(topic=None)
        reply = await read_event_share_text(
            42, _admin=SimpleNamespace(), session=session, settings=settings,
        )
        self.assertNotIn("Тема мероприятия:", reply.text)
        self.assertIn("startapp=event_42", reply.text)

    async def test_draft_is_not_shared(self):
        session, settings = self.make_context(status=EventStatus.DRAFT)
        with self.assertRaises(HTTPException) as cm:
            await read_event_share_text(
                42, _admin=SimpleNamespace(), session=session, settings=settings,
            )
        self.assertEqual(cm.exception.status_code, 409)
