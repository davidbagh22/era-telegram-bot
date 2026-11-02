"""Regression guards for untrusted event-activity callback and recovered FSM IDs.

Isolated mocks only: no production Telegram, database, registrations or points.
"""
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

from app.handlers.participant.events import event_activity_start, event_activity_submit
from app.states.event import EventActivityStates


def _user():
    return SimpleNamespace(
        id=7, first_name="Участник", last_name=None,
        application_status="approved", is_blocked=False, is_archived=False,
    )


def _state(data=None):
    return SimpleNamespace(
        get_data=AsyncMock(return_value={} if data is None else data),
        set_state=AsyncMock(), update_data=AsyncMock(), clear=AsyncMock(),
    )


class EventActivityCallbackFsmBoundsTests(IsolatedAsyncioTestCase):
    async def test_malformed_start_callback_never_queries_or_opens_fsm(self):
        invalid = (
            "event:activity:", "event:activity:0", "event:activity:-1",
            "event:activity:2147483648", "event:activity:９",
            "event:activity:abc", "event:activity:42:extra",
            "event:activity:" + "9" * 5000,
        )
        for payload in invalid:
            with self.subTest(payload=payload[:40]):
                call = SimpleNamespace(
                    data=payload, answer=AsyncMock(),
                    message=SimpleNamespace(answer=AsyncMock()),
                )
                session = SimpleNamespace(get=AsyncMock(), scalar=AsyncMock(), add=MagicMock())
                state = _state()
                await event_activity_start(call, _user(), session, state)
                call.answer.assert_awaited_once()
                session.get.assert_not_awaited()
                session.scalar.assert_not_awaited()
                session.add.assert_not_called()
                state.set_state.assert_not_awaited()
                state.update_data.assert_not_awaited()
                call.message.answer.assert_awaited_once()

    async def test_corrupted_submit_fsm_id_never_queries_or_notifies(self):
        for value in (None, True, False, -1, 0, 2147483648, "bad", "９", "9" * 5000):
            with self.subTest(value=str(value)[:40]):
                message = SimpleNamespace(answer=AsyncMock())
                state = _state({"event_activity_id": value})
                session = SimpleNamespace(get=AsyncMock(), scalar=AsyncMock(), add=MagicMock())
                with patch(
                    "app.handlers.participant.events.notify_admins",
                    new_callable=AsyncMock,
                ) as notify:
                    await event_activity_submit(
                        message, _user(), session, state,
                        SimpleNamespace(), SimpleNamespace(),
                    )
                session.get.assert_not_awaited()
                session.scalar.assert_not_awaited()
                session.add.assert_not_called()
                notify.assert_not_awaited()
                state.clear.assert_awaited_once()
                message.answer.assert_awaited_once()

    async def test_valid_start_preserves_registration_and_duplicate_checks(self):
        call = SimpleNamespace(
            data="event:activity:00042", answer=AsyncMock(),
            message=SimpleNamespace(answer=AsyncMock()),
        )
        activity = SimpleNamespace(
            id=42, event_id=13, is_active=True, deadline=None,
            title="Активность", description="Описание", points=5,
            submission_type="text",
        )
        session = SimpleNamespace(
            get=AsyncMock(return_value=activity),
            scalar=AsyncMock(side_effect=[SimpleNamespace(event_id=13), None]),
        )
        state = _state()
        await event_activity_start(call, _user(), session, state)
        session.get.assert_awaited_once()
        self.assertEqual(session.scalar.await_count, 2)
        state.set_state.assert_awaited_once_with(EventActivityStates.submission)
        state.update_data.assert_awaited_once_with(event_activity_id=42)
        call.message.answer.assert_awaited_once()
