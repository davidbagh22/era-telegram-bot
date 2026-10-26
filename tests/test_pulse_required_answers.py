from __future__ import annotations

import unittest
from unittest.mock import AsyncMock

from app.handlers.pulse_private import first_missing_required, show


class PulseRequiredAnswerTests(unittest.IsolatedAsyncioTestCase):
    def test_first_missing_required_finds_unanswered_question(self):
        data = {
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
        data = {
            "questions": [
                {"key": "done", "required": True},
                {"key": "optional", "required": False},
            ],
            "draft": {"done": "Всё учтено"},
        }
        self.assertIsNone(first_missing_required(data))

    async def test_free_text_question_explicitly_requests_a_message(self):
        message = AsyncMock()
        data = {
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
        data = {
            "index": 0,
            "questions": [{"key": "done", "text": "Что сделано?", "required": True, "choices": ["Всё учтено"]}],
            "draft": {},
        }
        await show(message, data)
        self.assertIn("Выбери кнопку ниже или напиши ответ", message.answer.await_args.args[0])
