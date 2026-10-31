"""Guard supplemental event activity start against ineligible or duplicate submissions.

Isolated mocks only: no real Telegram API, database, participants, or points.
The test preserves current registration policy; waitlist eligibility is a separate
business-rule review and must not be inferred from these cases.
"""
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from app.database.models import EventActivity
from app.handlers.participant.events import event_activity_start


def _call():
    return SimpleNamespace(
        data="event:activity:42",
        answer=AsyncMock(),
        message=SimpleNamespace(answer=AsyncMock()),
    )


def _state():
    return SimpleNamespace(set_state=AsyncMock(), update_data=AsyncMock())


def _activity(**changes):
    values = dict(
        id=42, event_id=13, is_active=True, deadline=None,
        submission_type="text", title="Активность", description="Описание",
        points=5,
    )
    values.update(changes)
    return SimpleNamespace(**values)


class ActivityStartEligibilityTests(IsolatedAsyncioTestCase):
    async def test_unapproved_actor_does_not_access_database_or_fsm(self):
        call, state = _call(), _state()
        session = SimpleNamespace(get=AsyncMock(), scalar=AsyncMock())
        with patch("app.handlers.participant.events._approved", return_value=False):
            await event_activity_start(call, None, session, state)
        call.answer.assert_awaited_once()
        session.get.assert_not_awaited()
        session.scalar.assert_not_awaited()
        state.set_state.assert_not_awaited()
        state.update_data.assert_not_awaited()

    async def test_closed_or_expired_activity_does_not_start_submission(self):
        expired = datetime.now().astimezone() - timedelta(days=1)
        for activity in (_activity(is_active=False), _activity(deadline=expired)):
            with self.subTest(activity=activity):
                call, state = _call(), _state()
                session = SimpleNamespace(
                    get=AsyncMock(return_value=activity), scalar=AsyncMock()
                )
                with patch("app.handlers.participant.events._approved", return_value=True):
                    await event_activity_start(call, SimpleNamespace(id=7), session, state)
                session.get.assert_awaited_once_with(EventActivity, 42)
                session.scalar.assert_not_awaited()
                state.set_state.assert_not_awaited()
                state.update_data.assert_not_awaited()
                call.message.answer.assert_awaited_once()

    async def test_unregistered_user_cannot_start_submission(self):
        call, state = _call(), _state()
        session = SimpleNamespace(
            get=AsyncMock(return_value=_activity()),
            scalar=AsyncMock(return_value=None),
        )
        with patch("app.handlers.participant.events._approved", return_value=True):
            await event_activity_start(call, SimpleNamespace(id=7), session, state)
        session.scalar.assert_awaited_once()
        self.assertIn("Активность доступна участникам", call.message.answer.await_args.args[0])
        state.set_state.assert_not_awaited()
        state.update_data.assert_not_awaited()

    async def test_pending_or_approved_submissions_are_not_reopened(self):
        for status in ("pending", "approved"):
            with self.subTest(status=status):
                call, state = _call(), _state()
                session = SimpleNamespace(
                    get=AsyncMock(return_value=_activity()),
                    scalar=AsyncMock(side_effect=[
                        SimpleNamespace(event_id=13, user_id=7),
                        SimpleNamespace(status=status),
                    ]),
                )
                with patch("app.handlers.participant.events._approved", return_value=True):
                    await event_activity_start(call, SimpleNamespace(id=7), session, state)
                self.assertEqual(session.scalar.await_count, 2)
                self.assertIn("уже сохранён", call.message.answer.await_args.args[0])
                state.set_state.assert_not_awaited()
                state.update_data.assert_not_awaited()

    async def test_rejected_submission_may_reenter_existing_review_flow(self):
        call, state = _call(), _state()
        session = SimpleNamespace(
            get=AsyncMock(return_value=_activity()),
            scalar=AsyncMock(side_effect=[
                SimpleNamespace(event_id=13, user_id=7),
                SimpleNamespace(status="rejected"),
            ]),
        )
        with patch("app.handlers.participant.events._approved", return_value=True):
            await event_activity_start(call, SimpleNamespace(id=7), session, state)
        state.set_state.assert_awaited_once()
        state.update_data.assert_awaited_once_with(event_activity_id=42)
        self.assertIn("5 баллов", call.message.answer.await_args.args[0])
