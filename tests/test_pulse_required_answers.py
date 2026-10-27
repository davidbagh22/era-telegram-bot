from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.handlers.pulse_private import first_missing_required, pulse_action, show


class PulseRequiredAnswerTests(unittest.IsolatedAsyncioTestCase):
    def test_first_missing_required_finds_unanswered_question(self):
        data = {"cycle_id": 55,
            "index": 3,
            "questions": [
                {"key": "done", "required": True},
                {"key": "optional", "required": False},
                {"key": "plans", "required": True},
            ],
            "draft": {"done": "Всё учтено", "plans": "  "},
        }
        self.assertEqual(first_missing_required(data), 2)

    def test_all_required_answers_are_present(self):
        data = {"cycle_id": 55,
            "questions": [
                {"key": "done", "required": True},
                {"key": "optional", "required": False},
            ],
            "draft": {"done": "Всё учтено"},
        }
        self.assertIsNone(first_missing_required(data))

    async def test_free_text_question_explicitly_requests_a_message(self):
        message = AsyncMock()
        data = {"cycle_id": 55,
            "index": 0,
            "questions": [{"key": "result", "text": "Какой результат?", "required": True, "choices": []}],
            "draft": {},
        }
        await show(message, data)
        text = message.answer.await_args.args[0]
        self.assertIn("Напиши ответ сообщением", text)
        self.assertIn("1/1", text)

    async def test_choice_question_explains_both_input_methods(self):
        message = AsyncMock()
        data = {"cycle_id": 55,
            "index": 0,
            "questions": [{"key": "done", "text": "Что сделано?", "required": True, "choices": ["Всё учтено"]}],
            "draft": {},
        }
        await show(message, data)
        self.assertIn("Выбери кнопку ниже или напиши ответ", message.answer.await_args.args[0])

    async def test_submit_with_missing_required_answer_returns_to_question(self):
        data = {"cycle_id": 55,
            "index": 2,
            "questions": [
                {"key": "done", "text": "Что сделано?", "required": True},
                {"key": "plans", "text": "Что дальше?", "required": True},
            ],
            "draft": {"done": "Всё учтено"},
        }
        pulse = SimpleNamespace(answers_json=data)
        view = SimpleNamespace(pulse=pulse, report=SimpleNamespace(submitted_at=None))
        call = SimpleNamespace(
            from_user=SimpleNamespace(id=11),
            message=AsyncMock(),
            data="pulse_form:submit:55:2",
            answer=AsyncMock(),
        )
        session = SimpleNamespace(flush=AsyncMock(), refresh=AsyncMock())
        settings = SimpleNamespace(leaders_chat_id=-100123)
        user = SimpleNamespace(id=9)
        with (
            patch("app.handlers.pulse_private.access", new_callable=AsyncMock, return_value=True),
            patch("app.handlers.pulse_private.current_form", new_callable=AsyncMock, return_value=(SimpleNamespace(id=55), view, data)),
            patch("app.handlers.pulse_private.show", new_callable=AsyncMock) as show_mock,
        ):
            await pulse_action(call, AsyncMock(), None, settings, session, user)
        self.assertEqual(pulse.answers_json["index"], 1)
        session.flush.assert_awaited_once()
        self.assertTrue(call.answer.await_args.kwargs["show_alert"])
        show_mock.assert_awaited_once()
