from __future__ import annotations

import unittest
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.handlers.pulse_private import pulse_action


class PulseRepeatSubmissionTests(unittest.IsolatedAsyncioTestCase):
    def _form(self):
        draft = {"done": "Всё учтено", "result": "Отчёт"}
        data = {
            "cycle_id": 42,
            "index": 2,
            "questions": [
                {"key": "done", "text": "Что сделано?", "required": True},
                {"key": "result", "text": "Результат?", "required": True},
            ],
            "draft": dict(draft),
            "attachments": {"result": "photo-1"},
            "submitted": dict(draft),
            "submitted_attachments": {"result": "photo-1"},
        }
        view = SimpleNamespace(
            report=SimpleNamespace(id=12, submitted_at=datetime.now(timezone.utc)),
            pulse=SimpleNamespace(answers_json=data),
        )
        cycle = SimpleNamespace(id=42, date_from=date(2026, 10, 26))
        return cycle, view, data

    async def _submit(self, cycle, view, *, refresh_side_effect=None):
        call = SimpleNamespace(
            data="pulse_form:submit:42:2",
            from_user=SimpleNamespace(id=77),
            message=SimpleNamespace(answer=AsyncMock()),
            answer=AsyncMock(),
        )
        state = SimpleNamespace(clear=AsyncMock())
        session = SimpleNamespace(
            flush=AsyncMock(), refresh=AsyncMock(side_effect=refresh_side_effect)
        )
        with (
            patch("app.handlers.pulse_private.access", new_callable=AsyncMock, return_value=True),
            patch("app.handlers.pulse_private.current_form", new_callable=AsyncMock,
                  return_value=(cycle, view, view.pulse.answers_json)),
            patch("app.handlers.pulse_private.submit_weekly_pulse", new_callable=AsyncMock) as submit,
            patch("app.handlers.pulse_private.mark_cycle_participant_submitted", new_callable=AsyncMock) as mark,
            patch("app.handlers.pulse_private.create_inboxes", new_callable=AsyncMock) as inbox,
        ):
            await pulse_action(
                call, state, None, SimpleNamespace(leaders_chat_id=-100123),
                session, SimpleNamespace(id=9),
            )
        return call, state, session, submit, mark, inbox

    async def test_repeated_preview_submit_does_not_repeat_side_effects(self):
        cycle, view, data = self._form()
        original = dict(data)
        call, state, session, submit, mark, inbox = await self._submit(cycle, view)
        submit.assert_not_awaited()
        mark.assert_not_awaited()
        inbox.assert_not_awaited()
        session.flush.assert_not_awaited()
        self.assertEqual(session.refresh.await_count, 2)
        self.assertIs(session.refresh.await_args_list[0].args[0], view.pulse)
        self.assertEqual(session.refresh.await_args_list[0].kwargs, {"with_for_update": True})
        self.assertIs(session.refresh.await_args_list[1].args[0], view.report)
        state.clear.assert_not_awaited()
        call.message.answer.assert_not_awaited()
        call.answer.assert_awaited_once_with("Этот Пульс уже отправлен.")
        self.assertEqual(view.pulse.answers_json, original)

    async def test_changed_attachment_allows_explicit_resubmission(self):
        cycle, view, data = self._form()
        data["attachments"]["result"] = "photo-2"
        call, state, _session, submit, mark, inbox = await self._submit(cycle, view)
        submit.assert_awaited_once()
        mark.assert_awaited_once()
        inbox.assert_awaited_once()
        state.clear.assert_awaited_once()
        call.answer.assert_awaited_once_with()
        self.assertEqual(view.pulse.answers_json["submitted_attachments"]["result"], "photo-2")
        call.message.answer.assert_awaited_once()

    async def test_changed_answer_allows_explicit_resubmission(self):
        cycle, view, data = self._form()
        data["draft"]["result"] = "Уточнённый отчёт"
        _call, _state, _session, submit, mark, inbox = await self._submit(cycle, view)
        submit.assert_awaited_once()
        mark.assert_awaited_once()
        inbox.assert_awaited_once()
        self.assertEqual(view.pulse.answers_json["submitted"]["result"], "Уточнённый отчёт")

    async def test_concurrent_duplicate_rechecks_persisted_state_under_lock(self):
        cycle, view, data = self._form()
        # This callback initially sees an unsubmitted report. Another handler
        # commits the same draft while the callback waits for the pulse lock.
        view.report.submitted_at = None
        data.pop("submitted")
        data.pop("submitted_attachments")

        async def refresh(obj, **kwargs):
            if obj is view.pulse:
                self.assertEqual(kwargs, {"with_for_update": True})
                data["submitted"] = dict(data["draft"])
                data["submitted_attachments"] = dict(data["attachments"])
            elif obj is view.report:
                view.report.submitted_at = datetime.now(timezone.utc)

        call, state, session, submit, mark, inbox = await self._submit(
            cycle, view, refresh_side_effect=refresh
        )
        self.assertEqual(session.refresh.await_count, 2)
        submit.assert_not_awaited()
        mark.assert_not_awaited()
        inbox.assert_not_awaited()
        session.flush.assert_not_awaited()
        state.clear.assert_not_awaited()
        call.answer.assert_awaited_once_with("Этот Пульс уже отправлен.")

    async def test_changed_draft_after_lock_still_resubmits(self):
        cycle, view, data = self._form()
        data["draft"]["result"] = "Уточнение после первой отправки"
        call, state, session, submit, mark, inbox = await self._submit(cycle, view)
        self.assertEqual(session.refresh.await_count, 2)
        submit.assert_awaited_once()
        mark.assert_awaited_once()
        inbox.assert_awaited_once()
        state.clear.assert_awaited_once()
        call.answer.assert_awaited_once_with()
