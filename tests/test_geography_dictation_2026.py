"""Partner event semantics, anti-duplicate guard and Telegram presentation."""
from datetime import date, time
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, Mock

from app.services.event_announcement_format import event_topic_html
from app.services.geography_dictation_2026 import (
    DATE, DESCRIPTION, LOCATION, MARKER, REGISTRATION_URL, TITLE,
    _publish_locked,
)


class GeographyDictationPresentationTests(TestCase):
    def test_exact_approved_schedule_and_external_registration(self):
        self.assertEqual(DATE, date(2026, 11, 22))
        self.assertEqual(LOCATION, "Русский дом, Ереван")
        self.assertEqual(REGISTRATION_URL, "https://t.me/+quri_BnuHaxjZTVi")

    def test_topic_uses_hyperlink_and_no_era_certificate_claim(self):
        event = SimpleNamespace(
            title=TITLE, description=DESCRIPTION, event_date=DATE, event_time=time(12),
            location=LOCATION, additional_info=MARKER,
        )
        experience = SimpleNamespace(
            full_description=DESCRIPTION, end_time=None,
            registration_url=REGISTRATION_URL,
        )
        result = event_topic_html(
            event, experience, registration=REGISTRATION_URL,
            chat="https://t.me/+group", topic="https://t.me/c/123/777",
        )
        self.assertIn("<b>Географический диктант — 2026</b>", result)
        self.assertIn(">Зарегистрироваться</a>", result)
        self.assertIn("по ссылке организаторов", result)
        self.assertNotIn("сертификат", result.lower())
        self.assertNotIn("startapp=event_", result)


class GeographyDictationIdempotenceTests(IsolatedAsyncioTestCase):
    async def test_preexisting_same_title_without_marker_is_not_duplicated(self):
        already = SimpleNamespace(title=TITLE, additional_info="other-workflow", event_date=DATE)
        session = SimpleNamespace(
            scalar=AsyncMock(return_value=None),
            scalars=AsyncMock(return_value=[already]),
            add=Mock(), commit=AsyncMock(), get=AsyncMock(),
        )
        await _publish_locked(bot=None, settings=SimpleNamespace(), session=session)
        session.add.assert_not_called()
        session.commit.assert_not_awaited()
