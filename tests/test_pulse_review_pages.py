from __future__ import annotations

import unittest
from unittest.mock import AsyncMock

from app.handlers.pulse_private import preview_pages, show


class PulseReviewPagesTests(unittest.IsolatedAsyncioTestCase):
    async def test_long_review_is_split_and_submit_only_on_final_page(self):
        data = {
            "index": 45,
            "questions": [
                {"key": f"answer_{i}", "text": f"Вопрос {i}: " + "&" * 260, "required": True}
                for i in range(45)
            ],
            "draft": {f"answer_{i}": "<" + "&" * 118 for i in range(45)},
        }
        message = AsyncMock()
        await show(message, data)
        calls = message.answer.await_args_list
        self.assertGreater(len(calls), 1)
        self.assertTrue(all(len(call.args[0]) <= 4096 for call in calls))
        self.assertTrue(all(call.kwargs.get("parse_mode") == "HTML" for call in calls))
        self.assertTrue(all(call.kwargs.get("reply_markup") is None for call in calls[:-1]))
        self.assertIsNotNone(calls[-1].kwargs["reply_markup"])
        self.assertIn("pulse_form:submit:45", [
            button.callback_data
            for row in calls[-1].kwargs["reply_markup"].inline_keyboard
            for button in row
        ])
        self.assertIn("&lt;", calls[0].args[0])
        self.assertNotIn("<&", calls[0].args[0])

    async def test_short_review_has_one_message_and_submit(self):
        data = {
            "index": 1,
            "questions": [{"key": "done", "text": "Что сделано?", "required": True}],
            "draft": {"done": "Готово"},
        }
        message = AsyncMock()
        await show(message, data)
        message.answer.assert_awaited_once()
        self.assertIsNotNone(message.answer.await_args.kwargs["reply_markup"])

    def test_each_page_stays_under_limit_even_with_html_escaping(self):
        data = {
            "index": 20,
            "questions": [
                {"key": str(i), "text": "&" * 1000, "required": True}
                for i in range(20)
            ],
            "draft": {str(i): "&" * 2000 for i in range(20)},
        }
        pages = preview_pages(data)
        self.assertGreater(len(pages), 1)
        self.assertTrue(all(len(page) <= 3500 for page in pages))
