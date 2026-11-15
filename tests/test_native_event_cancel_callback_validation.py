"""Malformed native event-cancellation callbacks must not trigger a 500.

Pure parser and mocked handler only; no Telegram API or database writes.
"""
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch

from app.handlers.participant.event_plans_changed import (
    _event_id_from_callback,
    plans_changed,
)


class EventPlansCallbackParserTests(TestCase):
    def test_valid_positive_event_ids(self):
        self.assertEqual(_event_id_from_callback("event:plans_changed:42"), 42)
        self.assertEqual(_event_id_from_callback("event:plans_changed:0005"), 5)
        self.assertEqual(_event_id_from_callback("event:plans_changed:2147483647"), 2_147_483_647)

    def test_rejects_malformed_or_out_of_range_callback_ids(self):
        for value in (
            None,
            "",
            "event:plans_changed:",
            "event:plans_changed:0",
            "event:plans_changed:2147483648",
            "event:plans_changed:-1",
            "event:plans_changed:abc",
            "event:plans_changed:1:2",
            "event:plans_changed:1 OR 1=1",
            "event:plans_changed:１２",
            "event:plans_changed:" + "9" * 200,
            "other:plans_changed:42",
        ):
            with self.subTest(value=value):
                self.assertIsNone(_event_id_from_callback(value))


class EventPlansCallbackHandlerTests(IsolatedAsyncioTestCase):
    async def test_bad_callback_returns_safe_message_without_db_query(self):
        call = SimpleNamespace(
            data="event:plans_changed:broken",
            message=SimpleNamespace(answer=AsyncMock()),
        )
        user = SimpleNamespace(id=7)
        session = SimpleNamespace(scalar=AsyncMock(), get=AsyncMock())
        with patch(
            "app.handlers.participant.event_plans_changed._guard",
            new=AsyncMock(return_value=True),
        ):
            await plans_changed(call, user, session)
        session.scalar.assert_not_awaited()
        session.get.assert_not_awaited()
        call.message.answer.assert_awaited_once()
        self.assertIn("Не удалось открыть регистрацию", call.message.answer.await_args.args[0])
