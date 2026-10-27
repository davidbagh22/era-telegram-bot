from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.handlers.pulse_private import answer_pulse, update_activity_followup


class PulseTypedInactivityTests(unittest.IsolatedAsyncioTestCase):
    def _form(self):
        data = {
            "cycle_id": 42,
            "index": 0,
            "questions": [
                {"key": "done", "text": "Что сделано?", "required": True,
                 "choices": ["Всё учтено", "Не было активности"]},
                {"key": "result", "text": "Какой результат?", "required": True, "choices": []},
            ],
            "draft": {},
        }
        view = SimpleNamespace(pulse=SimpleNamespace(answers_json=data))
        return view, data

    async def _type_answer(self, view, text):
        message = SimpleNamespace(
            text=text, caption=None, document=None, photo=None,
            from_user=SimpleNamespace(id=77), answer=AsyncMock(),
        )
        session = SimpleNamespace(flush=AsyncMock())
        with (
            patch("app.handlers.pulse_private.access", new_callable=AsyncMock, return_value=True),
            patch("app.handlers.pulse_private.current_form", new_callable=AsyncMock,
                  side_effect=lambda *_args: (SimpleNamespace(id=42), view, view.pulse.answers_json)),
            patch("app.handlers.pulse_private.show", new_callable=AsyncMock) as show,
        ):
            await answer_pulse(
                message, AsyncMock(), None,
                SimpleNamespace(leaders_chat_id=-100123), session,
                SimpleNamespace(id=9),
            )
        session.flush.assert_awaited_once()
        show.assert_awaited_once()
        return view.pulse.answers_json

    async def test_typed_inactivity_prompts_for_reason(self):
        view, _ = self._form()
        data = await self._type_answer(view, "Не было активности")
        self.assertEqual(data["draft"]["done"], "Не было активности")
        self.assertEqual(data["index"], 1)
        self.assertIn("Почему не было активности", data["questions"][1]["text"])
        self.assertEqual(data["original_result_question"]["text"], "Какой результат?")

    async def test_typed_correction_restores_result_question(self):
        view, data = self._form()
        update_activity_followup(data, question_index=0, selected="Не было активности")
        data["draft"] = {"done": "Не было активности", "result": "Не было задач"}
        data["index"] = 0
        updated = await self._type_answer(view, "Всё учтено")
        self.assertEqual(updated["questions"][1]["text"], "Какой результат?")
        self.assertNotIn("result", updated["draft"])
        self.assertNotIn("original_result_question", updated)
        self.assertEqual(updated["draft"]["done"], "Всё учтено")

    async def test_other_typed_result_keeps_custom_question(self):
        view, _ = self._form()
        updated = await self._type_answer(view, "Завершил проект")
        self.assertEqual(updated["draft"]["done"], "Завершил проект")
        self.assertEqual(updated["questions"][1]["text"], "Какой результат?")
        self.assertNotIn("original_result_question", updated)

    async def test_typed_custom_correction_clears_stale_inactivity_reason(self):
        view, data = self._form()
        update_activity_followup(data, question_index=0, selected="Не было активности")
        data["draft"] = {"done": "Не было активности", "result": "Не было задач"}
        data["index"] = 0
        updated = await self._type_answer(view, "Завершил проект")
        self.assertEqual(updated["draft"]["done"], "Завершил проект")
        self.assertNotIn("result", updated["draft"])
        self.assertEqual(updated["questions"][1]["text"], "Какой результат?")
        self.assertNotIn("original_result_question", updated)

    async def test_typed_custom_correction_after_choice_clears_old_result(self):
        view, data = self._form()
        data["draft"] = {"done": "Всё учтено", "result": "Старый результат"}
        data["index"] = 0
        updated = await self._type_answer(view, "Выполнил новую задачу")
        self.assertEqual(updated["draft"]["done"], "Выполнил новую задачу")
        self.assertNotIn("result", updated["draft"])
        self.assertEqual(updated["questions"][1]["text"], "Какой результат?")
