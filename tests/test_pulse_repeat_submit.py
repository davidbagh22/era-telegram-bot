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

    async def _submit(self, cycle, view):
        call = SimpleNamespace(
            data="pulse_form:submit:42:2",
            from_user=SimpleNamespace(id=77),
            message=SimpleNamespace(answer=AsyncMock()),
            answer=AsyncMock(),
        )
        state = SimpleNamespace(clear=AsyncMock())
        session = SimpleNamespace(flush=AsyncMock())
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
        self.assertEqual(data["submitted_attachments"]["result"], "photo-2")
        call.message.answer.assert_awaited_once()

    async def test_changed_answer_allows_explicit_resubmission(self):
        cycle, view, data = self._form()
        data["draft"]["result"] = "Уточнённый отчёт"
        _call, _state, _session, submit, mark, inbox = await self._submit(cycle, view)
        submit.assert_awaited_once()
        mark.assert_awaited_once()
        inbox.assert_awaited_once()
        self.assertEqual(data["submitted"]["result"], "Уточнённый отчёт")
