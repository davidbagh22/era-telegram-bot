"""Reject malformed feedback rating callback payloads before mutating FSM state.

All callbacks are mocked; no Telegram API, PostgreSQL or user data changes.
"""
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock

from app.handlers.participant.events import feedback_rating
from app.states.event import FeedbackStates


class FeedbackRatingCallbackValidationTests(IsolatedAsyncioTestCase):
    async def test_invalid_rating_does_not_mutate_state(self):
        invalid = (
            "", "feedback:rating:", "feedback:rating:0", "feedback:rating:6",
            "feedback:rating:-1", "feedback:rating:bad",
            "feedback:rating:１", "feedback:rating:01",
            "feedback:rating:5:extra", "feedback:rating:" + "9" * 5000,
        )
        for payload in invalid:
            with self.subTest(payload=payload[:40]):
                call = SimpleNamespace(
                    data=payload, answer=AsyncMock(),
                    message=SimpleNamespace(answer=AsyncMock()),
                )
                state = SimpleNamespace(update_data=AsyncMock(), set_state=AsyncMock())
                await feedback_rating(call, state)
                call.answer.assert_awaited_once()
                call.message.answer.assert_awaited_once()
                state.update_data.assert_not_awaited()
                state.set_state.assert_not_awaited()

    async def test_valid_one_to_five_preserves_existing_flow(self):
        for rating in range(1, 6):
            with self.subTest(rating=rating):
                call = SimpleNamespace(
                    data=f"feedback:rating:{rating}", answer=AsyncMock(),
                    message=SimpleNamespace(answer=AsyncMock()),
                )
                state = SimpleNamespace(update_data=AsyncMock(), set_state=AsyncMock())
                await feedback_rating(call, state)
                call.answer.assert_awaited_once()
                state.update_data.assert_awaited_once_with(rating=rating)
                state.set_state.assert_awaited_once_with(FeedbackStates.liked)
                call.message.answer.assert_awaited_once()
