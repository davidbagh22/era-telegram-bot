"""Supplemental event activity callbacks and recovered FSM IDs are bounded.

Mock-only tests: no real Telegram, PostgreSQL, submissions, or points.
"""
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from app.database.models import EventActivity
from app.handlers.participant.events import event_activity_start, event_activity_submit


class SupplementalActivityIdGuardTests(IsolatedAsyncioTestCase):
    async def test_invalid_callback_rejected_before_database_or_state(self):
        for suffix in ("", "0", "-1", "bad", "2147483648", "９", "9" * 5000):
            with self.subTest(suffix=suffix[:20]):
                call = SimpleNamespace(
                    data="event:activity:" + suffix,
                    answer=AsyncMock(),
                    message=SimpleNamespace(answer=AsyncMock()),
                )
                session = SimpleNamespace(get=AsyncMock(), scalar=AsyncMock())
                state = SimpleNamespace(set_state=AsyncMock(), update_data=AsyncMock())
                with patch("app.handlers.participant.events._approved", return_value=True):
                    await event_activity_start(call, SimpleNamespace(id=1), session, state)
                call.answer.assert_awaited_once()
                call.message.answer.assert_awaited_once()
                session.get.assert_not_awaited()
                session.scalar.assert_not_awaited()
                state.set_state.assert_not_awaited()
                state.update_data.assert_not_awaited()

    async def test_valid_callback_preserves_existing_lookup(self):
        call = SimpleNamespace(
            data="event:activity:42",
            answer=AsyncMock(),
            message=SimpleNamespace(answer=AsyncMock()),
        )
        session = SimpleNamespace(get=AsyncMock(return_value=None), scalar=AsyncMock())
        state = SimpleNamespace(set_state=AsyncMock(), update_data=AsyncMock())
        with patch("app.handlers.participant.events._approved", return_value=True):
            await event_activity_start(call, SimpleNamespace(id=1), session, state)
        session.get.assert_awaited_once_with(EventActivity, 42)
        state.set_state.assert_not_awaited()

    async def test_invalid_fsm_id_cleared_before_database_or_submission(self):
        for value in (None, True, -1, "bad", "2147483648", "9" * 5000):
            with self.subTest(value=str(value)[:20]):
                message = SimpleNamespace(answer=AsyncMock())
                state = SimpleNamespace(
                    get_data=AsyncMock(return_value={"event_activity_id": value}),
                    clear=AsyncMock(),
                )
                session = SimpleNamespace(get=AsyncMock(), scalar=AsyncMock(), add=AsyncMock())
                await event_activity_submit(
                    message, SimpleNamespace(id=1), session, state,
                    SimpleNamespace(), SimpleNamespace(),
                )
                session.get.assert_not_awaited()
                session.scalar.assert_not_awaited()
                session.add.assert_not_awaited()
                state.clear.assert_awaited_once()
                message.answer.assert_awaited_once()

    async def test_valid_fsm_id_preserves_existing_lookup(self):
        message = SimpleNamespace(answer=AsyncMock())
        state = SimpleNamespace(
            get_data=AsyncMock(return_value={"event_activity_id": "42"}),
            clear=AsyncMock(),
        )
        session = SimpleNamespace(get=AsyncMock(return_value=None), scalar=AsyncMock())
        await event_activity_submit(
            message,
            SimpleNamespace(id=1, application_status="approved", is_blocked=False, is_archived=False),
            session, state, SimpleNamespace(), SimpleNamespace(),
        )
        session.get.assert_awaited_once_with(EventActivity, 42)
        state.clear.assert_awaited_once()
