"""Issue #598: only participants with active registrations can submit proofs.

Mock SQL to assert the whitelist is used at start and at stale FSM submit.
No real Telegram sends, database mutations, or point awards.
"""
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.dialects import postgresql
from app.handlers.participant.events import event_activity_start, event_activity_submit
from app.utils.constants import RegistrationStatus

ACTIVE = {"registered", "will_come", "attended"}
INACTIVE = {"waitlist", "not_coming", "no_show", "cancelled"}

def session_for(status):
    async def scalar(stmt):
        sql = str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
        if "event_registrations" in sql:
            assert all("'" + v + "'" in sql for v in ACTIVE), sql
            assert not any("'" + v + "'" in sql for v in INACTIVE), sql
            return SimpleNamespace(event_id=13, user_id=7) if status.value in ACTIVE else None
        return None
    activity = SimpleNamespace(id=42, event_id=13, is_active=True, deadline=None,
                              submission_type="text", title="Задание", description="Описание", points=5)
    return SimpleNamespace(get=AsyncMock(return_value=activity),
                           scalar=AsyncMock(side_effect=scalar), add=MagicMock())

def user():
    return SimpleNamespace(id=7, application_status="approved", is_blocked=False,
                           is_archived=False, first_name="Тест", last_name=None)

class RegistrationStatusTests(IsolatedAsyncioTestCase):
    async def test_start_rejects_inactive_statuses(self):
        for status in RegistrationStatus:
            with self.subTest(status=status):
                call = SimpleNamespace(data="event:activity:42", answer=AsyncMock(),
                                       message=SimpleNamespace(answer=AsyncMock()))
                state = SimpleNamespace(set_state=AsyncMock(), update_data=AsyncMock())
                await event_activity_start(call, user(), session_for(status), state)
                if status.value in ACTIVE:
                    state.set_state.assert_awaited_once()
                else:
                    state.set_state.assert_not_awaited()
                    self.assertIn("участникам", call.message.answer.await_args.args[0])

    async def test_stale_fsm_rejects_inactive_statuses(self):
        for status in RegistrationStatus:
            with self.subTest(status=status):
                session = session_for(status)
                msg = SimpleNamespace(text="материал", caption=None, photo=None,
                                      video=None, document=None, answer=AsyncMock())
                state = SimpleNamespace(get_data=AsyncMock(return_value={"event_activity_id":42}),
                                        clear=AsyncMock())
                with patch("app.handlers.participant.events.notify_admins", new_callable=AsyncMock) as notify:
                    await event_activity_submit(msg, user(), session, state, SimpleNamespace(), SimpleNamespace())
                if status.value in ACTIVE:
                    session.add.assert_called_once()
                    notify.assert_awaited_once()
                else:
                    session.add.assert_not_called()
                    notify.assert_not_awaited()
                    state.clear.assert_awaited_once()
                    self.assertIn("участникам", msg.answer.await_args.args[0])
