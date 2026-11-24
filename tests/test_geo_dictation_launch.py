"""The one-off geography event keeps external signup and never duplicates a card."""
from datetime import date, time
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch

from app.services.event_announcement_format import event_topic_html
from app.services.geo_dictation_launch import (
    DESCRIPTION, EVENT_DATE, KEY, PLACE, SIGNUP_URL, START_TIME, TITLE,
    _ensure_event_and_publish,
)
from app.utils.constants import EventStatus


class GeographyPresentationTests(TestCase):
    def test_owner_details_are_preserved(self):
        self.assertEqual(EVENT_DATE, date(2026, 11, 22))
        self.assertEqual(START_TIME, time(12))
        self.assertEqual(PLACE, "Русский дом")
        self.assertEqual(SIGNUP_URL, "https://t.me/+quri_BnuHaxjZTVi")

    def test_telegram_links_use_named_external_signup(self):
        event = SimpleNamespace(
            title=TITLE, description=DESCRIPTION, event_date=EVENT_DATE,
            event_time=START_TIME, location=PLACE, additional_info=KEY,
        )
        experience = SimpleNamespace(full_description=DESCRIPTION, end_time=None)
        text = event_topic_html(
            event, experience, registration=SIGNUP_URL,
            chat="https://t.me/+ERA", topic="https://t.me/c/123/456",
        )
        self.assertIn("🌍 <b>Географический диктант — 2026</b>", text)
        self.assertIn('<a href="https://t.me/+quri_BnuHaxjZTVi">Зарегистрироваться</a>', text)
        self.assertNotIn("startapp=event_", text)


class GeographyIdempotencyTests(IsolatedAsyncioTestCase):
    async def test_existing_published_event_does_not_send_again(self):
        event = SimpleNamespace(
            id=76, additional_info=KEY, status=EventStatus.REGISTRATION_OPEN
        )
        exp = SimpleNamespace(announcement_status="sent")
        session = SimpleNamespace(
            scalars=AsyncMock(return_value=[event]), get=AsyncMock(return_value=exp),
            commit=AsyncMock(),
        )
        with patch("app.services.geo_dictation_launch.publish_event_announcement", new_callable=AsyncMock) as publish:
            await _ensure_event_and_publish(SimpleNamespace(), SimpleNamespace(), session)
            publish.assert_not_awaited()
        session.commit.assert_not_awaited()

    async def test_unmanaged_duplicate_is_not_overwritten_or_announced(self):
        event = SimpleNamespace(
            id=77, additional_info="something-else",
            status=EventStatus.REGISTRATION_OPEN,
        )
        session = SimpleNamespace(
            scalars=AsyncMock(return_value=[event]),
            get=AsyncMock(), commit=AsyncMock(),
        )
        with patch("app.services.geo_dictation_launch.publish_event_announcement", new_callable=AsyncMock) as publish:
            await _ensure_event_and_publish(SimpleNamespace(), SimpleNamespace(), session)
            publish.assert_not_awaited()
        session.get.assert_not_awaited()
