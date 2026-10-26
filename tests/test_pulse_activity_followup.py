from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.handlers.pulse_private import pulse_action, update_activity_followup


class PulseActivityFollowupTests(unittest.IsolatedAsyncioTestCase):
    def _data(self):
        return {
            "cycle_id": 77,
            "index": 0,
            "questions": [
                {"key": "done", "text": "Что сделано?", "required": True,
                 "choices": ["Всё учтено", "Не было активности"]},
                {"key": "result", "text": "Свой вопрос о результате", "required": False,
                 "choices": [], "audience": "all"},
                {"key": "plans", "text": "Что дальше?", "required": True, "choices": []},
            ],
            "draft": {},
        }

    def test_inactivity_question_is_reversible(self):
        data = self._data()
        update_activity_followup(data, question_index=0, selected="Не было активности")
        self.assertIn("Почему не было активности", data["questions"][1]["text"])
        self.assertTrue(data["questions"][1]["required"])
        self.assertEqual(data["original_result_question"]["text"], "Свой вопрос о результате")
        data["draft"] = {"done": "Не было активности", "result": "Не было задач"}
        update_activity_followup(data, question_index=0, selected="Всё учтено")
        self.assertEqual(data["questions"][1]["text"], "Свой вопрос о результате")
        self.assertFalse(data["questions"][1]["required"])
        self.assertNotIn("result", data["draft"])
        self.assertNotIn("original_result_question", data)

    def test_repeated_inactivity_keeps_original_question(self):
        data = self._data()
        update_activity_followup(data, question_index=0, selected="Не было активности")
        data["draft"] = {"done": "Не было активности", "result": "Был в поездке"}
        update_activity_followup(data, question_index=0, selected="Не было активности")
        self.assertEqual(data["draft"]["result"], "Был в поездке")
        self.assertEqual(data["original_result_question"]["text"], "Свой вопрос о результате")

    def test_custom_order_and_last_question_are_safe(self):
        data = self._data()
        data["questions"][1]["key"] = "projects"
        original = list(data["questions"])
        update_activity_followup(data, question_index=0, selected="Не было активности")
        self.assertEqual(data["questions"], original)
        data["questions"] = [data["questions"][0]]
        update_activity_followup(data, question_index=0, selected="Не было активности")
        self.assertEqual(len(data["questions"]), 1)

    async def test_callback_switch_restores_prompt_and_drops_stale_explanation(self):
        data = self._data()
        view = SimpleNamespace(pulse=SimpleNamespace(answers_json=data))
        cycle = SimpleNamespace(id=77)
        session = SimpleNamespace(flush=AsyncMock())
        settings = SimpleNamespace(leaders_chat_id=-100123)
        user = SimpleNamespace(id=9)
        state = AsyncMock()

        def callback(value):
            return SimpleNamespace(
                data=value,
                from_user=SimpleNamespace(id=11),
                message=AsyncMock(),
                answer=AsyncMock(),
            )

        async def current(*_args, **_kwargs):
            return cycle, view, view.pulse.answers_json

        with (
            patch("app.handlers.pulse_private.access", new_callable=AsyncMock, return_value=True),
            patch("app.handlers.pulse_private.current_form", side_effect=current),
            patch("app.handlers.pulse_private.show", new_callable=AsyncMock),
        ):
            await pulse_action(callback("pulse_form:choice:77:0:1"), state, None, settings, session, user)
            self.assertIn("Почему не было активности", view.pulse.answers_json["questions"][1]["text"])
            view.pulse.answers_json["draft"]["result"] = "Старая причина"
            await pulse_action(callback("pulse_form:back:77:1"), state, None, settings, session, user)
            await pulse_action(callback("pulse_form:choice:77:0:0"), state, None, settings, session, user)

        self.assertEqual(view.pulse.answers_json["questions"][1]["text"], "Свой вопрос о результате")
        self.assertNotIn("result", view.pulse.answers_json["draft"])
        self.assertEqual(view.pulse.answers_json["draft"]["done"], "Всё учтено")
        self.assertEqual(view.pulse.answers_json["index"], 1)
