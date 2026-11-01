"""Revalidate approval, activity and registration when a stale FSM proof arrives.

Isolated mocks only. No production Telegram, database, points or messages.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

from app.handlers.participant.events import event_activity_submit


def _user(**changes):
    values = dict(
        id=7, first_name="Участник", last_name=None,
        application_status="approved", is_blocked=False, is_archived=False,
    )
    values.update(changes)
    return SimpleNamespace(**values)


def _activity(**changes):
    values = dict(
        id=42, event_id=13, is_active=True, deadline=None,
        submission_type="text", title="Активность", points=5,
    )
    values.update(changes)
    return SimpleNamespace(**values)


def _fixtures(activity=None, registration=None):
    message = SimpleNamespace(
        photo=None, video=None, document=None,
        text="Сохранить материал", caption=None, answer=AsyncMock(),
    )
    state = SimpleNamespace(
        get_data=AsyncMock(return_value={"event_activity_id": 42}),
        clear=AsyncMock(),
    )
    session = SimpleNamespace(
        get=AsyncMock(return_value=activity or _activity()),
        scalar=AsyncMock(return_value=registration),
        add=MagicMock(),
    )
    return message, state, session


class ActivitySubmissionEligibilityTests(IsolatedAsyncioTestCase):
    async def test_revoked_approval_or_blocked_account_cannot_submit(self):
        for user in (
            None,
            _user(application_status="pending"),
            _user(is_blocked=True),
            _user(is_archived=True),
        ):
            with self.subTest(user=user):
                message, state, session = _fixtures()
                with patch(
                    "app.handlers.participant.events.notify_admins",
                    new_callable=AsyncMock,
                ) as notify:
                    await event_activity_submit(
                        message, user, session, state,
                        SimpleNamespace(), SimpleNamespace(),
                    )
                session.get.assert_not_awaited()
                session.scalar.assert_not_awaited()
                session.add.assert_not_called()
                notify.assert_not_awaited()
                state.clear.assert_awaited_once()
                self.assertIn("недоступна", message.answer.await_args.args[0])

    async def test_activity_deactivated_or_expired_after_fsm_start(self):
        expired = datetime.now().astimezone() - timedelta(minutes=1)
        for activity in (_activity(is_active=False), _activity(deadline=expired)):
            with self.subTest(activity=activity):
                message, state, session = _fixtures(activity=activity)
                with patch(
                    "app.handlers.participant.events.notify_admins",
                    new_callable=AsyncMock,
                ) as notify:
                    await event_activity_submit(
                        message, _user(), session, state,
                        SimpleNamespace(), SimpleNamespace(),
                    )
                session.get.assert_awaited_once()
                session.scalar.assert_not_awaited()
                session.add.assert_not_called()
                notify.assert_not_awaited()
                state.clear.assert_awaited_once()
                self.assertIn("закрыта", message.answer.await_args.args[0])

    async def test_legacy_naive_utc_deadline_rechecked_before_writes(self):
        now_utc_naive = datetime.now(timezone.utc).replace(tzinfo=None)
        for expired in (True, False):
            with self.subTest(expired=expired):
                deadline = now_utc_naive + timedelta(days=-1 if expired else 1)
                message, state, session = _fixtures(
                    activity=_activity(deadline=deadline)
                )
                session.scalar.side_effect = [
                    SimpleNamespace(event_id=13), None,
                ]
                with patch(
                    "app.handlers.participant.events.notify_admins",
                    new_callable=AsyncMock,
                ) as notify:
                    await event_activity_submit(
                        message, _user(), session, state,
                        SimpleNamespace(), SimpleNamespace(),
                    )
                state.clear.assert_awaited_once()
                if expired:
                    session.scalar.assert_not_awaited()
                    session.add.assert_not_called()
                    notify.assert_not_awaited()
                    self.assertIn("закрыта", message.answer.await_args.args[0])
                else:
                    self.assertEqual(session.scalar.await_count, 2)
                    session.add.assert_called_once()
                    notify.assert_awaited_once()

    async def test_registration_revoked_after_fsm_start(self):
        message, state, session = _fixtures(registration=None)
        with patch(
            "app.handlers.participant.events.notify_admins",
            new_callable=AsyncMock,
        ) as notify:
            await event_activity_submit(
                message, _user(), session, state,
                SimpleNamespace(), SimpleNamespace(),
            )
        session.scalar.assert_awaited_once()
        session.add.assert_not_called()
        notify.assert_not_awaited()
        state.clear.assert_awaited_once()
        self.assertIn("участникам мероприятия", message.answer.await_args.args[0])

    async def test_registered_participant_still_submits(self):
        message, state, session = _fixtures()
        session.scalar.side_effect = [SimpleNamespace(event_id=13), None]
        with patch(
            "app.handlers.participant.events.notify_admins",
            new_callable=AsyncMock,
        ) as notify:
            await event_activity_submit(
                message, _user(), session, state,
                SimpleNamespace(), SimpleNamespace(),
            )
        self.assertEqual(session.scalar.await_count, 2)
        session.add.assert_called_once()
        state.clear.assert_awaited_once()
        notify.assert_awaited_once()
        self.assertIn("в вашем профиле", message.answer.await_args.args[0])
