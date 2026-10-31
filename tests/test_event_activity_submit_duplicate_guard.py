"""Stale FSM activity messages cannot replace reviewed or pending evidence.

Isolated mocks: no real Telegram sends, production database, or points.
"""
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

from app.handlers.participant.events import event_activity_submit


def _fixtures(status):
    message = SimpleNamespace(
        photo=None, video=None, document=None,
        text="Попытка заменить материал", caption=None, answer=AsyncMock(),
    )
    state = SimpleNamespace(
        get_data=AsyncMock(return_value={"event_activity_id": 42}),
        clear=AsyncMock(),
    )
    activity = SimpleNamespace(
        id=42, event_id=13, is_active=True, deadline=None,
        submission_type="text", title="Активность", points=5,
    )
    existing = SimpleNamespace(
        status=status, text="Оригинальный материал",
        file_id=None, file_type=None,
    )
    session = SimpleNamespace(
        get=AsyncMock(return_value=activity),
        scalar=AsyncMock(side_effect=[SimpleNamespace(event_id=13), existing]),
        add=MagicMock(),
    )
    user = SimpleNamespace(id=7, first_name="Участник", last_name=None,
                           application_status="approved", is_blocked=False, is_archived=False)
    return message, state, session, user, existing


class ActivitySubmitDuplicateGuardTests(IsolatedAsyncioTestCase):
    async def test_pending_and_approved_submissions_cannot_be_overwritten(self):
        for status in ("pending", "approved"):
            with self.subTest(status=status):
                message, state, session, user, existing = _fixtures(status)
                with patch(
                    "app.handlers.participant.events.notify_admins",
                    new_callable=AsyncMock,
                ) as notify:
                    await event_activity_submit(
                        message, user, session, state,
                        SimpleNamespace(), SimpleNamespace(),
                    )
                self.assertEqual(existing.status, status)
                self.assertEqual(existing.text, "Оригинальный материал")
                self.assertIsNone(existing.file_id)
                state.clear.assert_awaited_once()
                session.add.assert_not_called()
                notify.assert_not_awaited()
                self.assertIn("уже сохранён", message.answer.await_args.args[0])

    async def test_rejected_submission_can_be_corrected_without_new_row(self):
        message, state, session, user, existing = _fixtures("rejected")
        with patch(
            "app.handlers.participant.events.notify_admins",
            new_callable=AsyncMock,
        ) as notify:
            await event_activity_submit(
                message, user, session, state,
                SimpleNamespace(), SimpleNamespace(),
            )
        self.assertEqual(existing.status, "pending")
        self.assertEqual(existing.text, "Попытка заменить материал")
        state.clear.assert_awaited_once()
        session.add.assert_not_called()
        notify.assert_awaited_once()
        self.assertIn("в вашем профиле", message.answer.await_args.args[0])
