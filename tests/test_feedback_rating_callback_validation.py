"""Reject malformed feedback rating callback payloads before mutating FSM state.

All callbacks are mocked; no Telegram API, PostgreSQL or user data changes.
"""
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock

from app.handlers.participant.events import feedback_improve, feedback_liked, feedback_rating
from app.states.event import FeedbackStates
from app.utils.constants import ApplicationStatus


def _approved_user():
    return SimpleNamespace(
        application_status=ApplicationStatus.APPROVED,
        is_blocked=False,
        is_archived=False,
    )


def _inactive_users():
    return (
        None,
        SimpleNamespace(application_status=ApplicationStatus.PENDING,
                        is_blocked=False, is_archived=False),
        SimpleNamespace(application_status=ApplicationStatus.REJECTED,
                        is_blocked=False, is_archived=False),
        SimpleNamespace(application_status=ApplicationStatus.APPROVED,
                        is_blocked=True, is_archived=False),
        SimpleNamespace(application_status=ApplicationStatus.APPROVED,
                        is_blocked=False, is_archived=True),
    )


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
                await feedback_rating(call, state, _approved_user())
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
                await feedback_rating(call, state, _approved_user())
                call.answer.assert_awaited_once()
                state.update_data.assert_awaited_once_with(rating=rating)
                state.set_state.assert_awaited_once_with(FeedbackStates.liked)
                call.message.answer.assert_awaited_once()


    async def test_revoked_user_cannot_advance_rating_step(self):
        for user in _inactive_users():
            with self.subTest(user=str(user)):
                call = SimpleNamespace(
                    data="feedback:rating:5", answer=AsyncMock(),
                    message=SimpleNamespace(answer=AsyncMock()),
                )
                state = SimpleNamespace(
                    update_data=AsyncMock(), set_state=AsyncMock(), clear=AsyncMock(),
                )
                await feedback_rating(call, state, user)
                call.answer.assert_awaited_once()
                state.clear.assert_awaited_once()
                state.update_data.assert_not_awaited()
                state.set_state.assert_not_awaited()
                call.message.answer.assert_awaited_once()

    async def test_revoked_user_cannot_advance_text_steps(self):
        for handler in (feedback_liked, feedback_improve):
            for user in _inactive_users():
                with self.subTest(handler=handler.__name__, user=str(user)):
                    message = SimpleNamespace(text="Спасибо", answer=AsyncMock())
                    state = SimpleNamespace(
                        update_data=AsyncMock(), set_state=AsyncMock(), clear=AsyncMock(),
                    )
                    await handler(message, state, user)
                    state.clear.assert_awaited_once()
                    state.update_data.assert_not_awaited()
                    state.set_state.assert_not_awaited()
                    message.answer.assert_awaited_once()

    async def test_approved_user_can_advance_text_steps(self):
        message = SimpleNamespace(text="Хорошо", answer=AsyncMock())
        state = SimpleNamespace(
            update_data=AsyncMock(), set_state=AsyncMock(), clear=AsyncMock(),
        )
        await feedback_liked(message, state, _approved_user())
        state.update_data.assert_awaited_once_with(liked="Хорошо")
        state.set_state.assert_awaited_once_with(FeedbackStates.improve)
        state.clear.assert_not_awaited()
        message.answer.assert_awaited_once()

        message = SimpleNamespace(text="Добавить время", answer=AsyncMock())
        state = SimpleNamespace(
            update_data=AsyncMock(), set_state=AsyncMock(), clear=AsyncMock(),
        )
        await feedback_improve(message, state, _approved_user())
        state.update_data.assert_awaited_once_with(improve="Добавить время")
        state.set_state.assert_awaited_once_with(FeedbackStates.wants_again)
        state.clear.assert_not_awaited()
        message.answer.assert_awaited_once()
