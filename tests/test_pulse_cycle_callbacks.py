from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.handlers.pulse_private import callback_matches_current_cycle, pulse_action


class PulseCycleCallbackTests(unittest.IsolatedAsyncioTestCase):
    def test_callback_matches_current_cycle_and_question(self):
        self.assertTrue(callback_matches_current_cycle(
            ["pulse_form", "choice", "56", "0", "1"], cycle_id=56, index=0,
        ))
        self.assertFalse(callback_matches_current_cycle(
            ["pulse_form", "choice", "55", "0", "1"], cycle_id=56, index=0,
        ))
        self.assertFalse(callback_matches_current_cycle(
            ["pulse_form", "choice", "56", "1", "1"], cycle_id=56, index=0,
        ))
        self.assertFalse(callback_matches_current_cycle(
            ["pulse_form", "choice", "0", "1"], cycle_id=56, index=0,
        ))

    async def _assert_stale_callback_does_not_change_answers(self, callback_data):
        data = {
            "cycle_id": 56,
            "index": 0,
            "questions": [
                {"key": "done", "text": "Что сделано?", "required": True, "choices": ["Готово"]},
            ],
            "draft": {},
        }
        pulse = SimpleNamespace(answers_json=data)
        view = SimpleNamespace(pulse=pulse)
        call = SimpleNamespace(
            from_user=SimpleNamespace(id=11),
            message=AsyncMock(),
            data=callback_data,
            answer=AsyncMock(),
        )
        session = SimpleNamespace(flush=AsyncMock())
        settings = SimpleNamespace(leaders_chat_id=-100123)
        user = SimpleNamespace(id=9)
        with (
            patch("app.handlers.pulse_private.access", new_callable=AsyncMock, return_value=True),
            patch("app.handlers.pulse_private.current_form", new_callable=AsyncMock, return_value=(SimpleNamespace(id=56), view, data)),
            patch("app.handlers.pulse_private.show", new_callable=AsyncMock) as show_mock,
        ):
            await pulse_action(call, AsyncMock(), None, settings, session, user)
        self.assertEqual(pulse.answers_json["draft"], {})
        self.assertEqual(pulse.answers_json["index"], 0)
        session.flush.assert_not_awaited()
        self.assertTrue(call.answer.await_args.kwargs["show_alert"])
        show_mock.assert_awaited_once()

    async def test_previous_week_button_is_rejected_even_at_same_index(self):
        await self._assert_stale_callback_does_not_change_answers("pulse_form:choice:55:0:0")

    async def test_legacy_button_is_rejected_without_mutating_draft(self):
        await self._assert_stale_callback_does_not_change_answers("pulse_form:choice:0:0")
