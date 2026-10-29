"""Invalid native event callback IDs must not reach PostgreSQL or Telegram sends.

Pure parser and mocked handler paths only; no real registrations or chats.
"""
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch

from app.handlers.participant.events_stability_block8 import (
    _event_id_from_callback,
    confirmation_code_start,
    event_calendar,
    event_join,
    event_view,
)


class NativeEventIdParserTests(TestCase):
    def test_valid_positive_postgres_ids(self):
        for prefix in ("event:view:", "event:join:", "event:calendar:", "event:confirm_code:"):
            with self.subTest(prefix=prefix):
                self.assertEqual(_event_id_from_callback(prefix + "00042", prefix), 42)
                self.assertEqual(_event_id_from_callback(prefix + "2147483647", prefix), 2_147_483_647)

    def test_rejects_invalid_or_oversized_ids(self):
        for prefix in ("event:view:", "event:join:", "event:calendar:", "event:confirm_code:"):
            for suffix in ("", "0", "-1", "2147483648", "bad", "1:2", "１２", "9" * 5000):
                with self.subTest(prefix=prefix, suffix=suffix):
                    self.assertIsNone(_event_id_from_callback(prefix + suffix, prefix))
            self.assertIsNone(_event_id_from_callback(None, prefix))
            self.assertIsNone(_event_id_from_callback("other:42", prefix))


class NativeEventHandlerIdTests(IsolatedAsyncioTestCase):
    async def test_bad_view_and_join_do_not_query_database(self):
        for handler, prefix in ((event_view, "event:view:"), (event_join, "event:join:")):
            with self.subTest(handler=handler.__name__):
                call = SimpleNamespace(
                    data=prefix + "2147483648",
                    answer=AsyncMock(),
                    message=SimpleNamespace(answer=AsyncMock()),
                )
                session = SimpleNamespace(get=AsyncMock(), scalar=AsyncMock())
                with patch("app.handlers.participant.events_stability_block8._approved", return_value=True):
                    await handler(call, SimpleNamespace(id=1), session)
                session.get.assert_not_awaited()
                session.scalar.assert_not_awaited()
                call.message.answer.assert_awaited_once()

    async def test_bad_calendar_does_not_query_database_or_send_document(self):
        call = SimpleNamespace(
            data="event:calendar:" + "9" * 5000,
            answer=AsyncMock(),
            message=SimpleNamespace(answer=AsyncMock()),
        )
        session = SimpleNamespace(get=AsyncMock(), scalar=AsyncMock())
        with patch("app.handlers.participant.events_stability_block8._approved", return_value=True):
            await event_calendar(call, SimpleNamespace(id=1), session, SimpleNamespace(timezone="Asia/Yerevan"))
        session.get.assert_not_awaited()
        session.scalar.assert_not_awaited()
        call.message.answer.assert_awaited_once()

    async def test_bad_attendance_code_event_id_never_queries_database(self):
        call = SimpleNamespace(
            data="event:confirm_code:2147483648",
            from_user=SimpleNamespace(id=1),
            answer=AsyncMock(),
            message=SimpleNamespace(answer=AsyncMock()),
        )
        session = SimpleNamespace(get=AsyncMock(), scalar=AsyncMock())
        state = SimpleNamespace(set_state=AsyncMock(), update_data=AsyncMock())
        with (
            patch("app.handlers.participant.events_stability_block8._approved", return_value=True),
            patch("app.services.event_attendance_service.attendance_v2_enabled", return_value=True),
        ):
            await confirmation_code_start(call, SimpleNamespace(id=1), SimpleNamespace(), session, state)
        session.get.assert_not_awaited()
        session.scalar.assert_not_awaited()
        state.set_state.assert_not_awaited()
        call.message.answer.assert_awaited_once()
