"""The activity receipt points to the existing profile, not removed My Path UI.

Mock-only: no Telegram sends, real activity, database write or points award.
"""
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

from app.handlers.participant.events import event_activity_submit


class ActivitySubmissionCopyTests(IsolatedAsyncioTestCase):
    async def test_success_message_refers_to_profile_without_obsolete_path(self):
        message = SimpleNamespace(
            photo=None, video=None, document=None,
            text="Готовый отчёт", caption=None, answer=AsyncMock(),
        )
        state = SimpleNamespace(
            get_data=AsyncMock(return_value={"event_activity_id": 42}),
            clear=AsyncMock(),
        )
        activity = SimpleNamespace(
            id=42, submission_type="text", title="Тестовая активность", points=10,
        )
        session = SimpleNamespace(
            get=AsyncMock(return_value=activity),
            scalar=AsyncMock(return_value=None),
            add=MagicMock(),
        )
        user = SimpleNamespace(id=7, first_name="Тест", last_name="Участник")
        with patch(
            "app.handlers.participant.events.notify_admins",
            new_callable=AsyncMock,
        ) as notify:
            await event_activity_submit(
                message, user, session, state, SimpleNamespace(), SimpleNamespace(),
            )
        message.answer.assert_awaited_once()
        reply = message.answer.await_args.args[0]
        self.assertIn("в вашем профиле", reply)
        self.assertNotIn("Моём пути", reply)
        state.clear.assert_awaited_once()
        session.add.assert_called_once()
        notify.assert_awaited_once()


if __name__ == "__main__":
    import unittest
    unittest.main()
