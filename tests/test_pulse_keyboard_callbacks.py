from __future__ import annotations

import unittest

from app.handlers.pulse_private import keyboard


class PulseKeyboardTests(unittest.TestCase):
    def test_choice_buttons_are_bound_to_current_question(self):
        data = {"cycle_id": 55, "index": 1, "questions": [
            {"key": "done", "required": True, "choices": ["Да"]},
            {"key": "blocker", "required": False, "choices": ["Нет", "Нужна помощь"]},
        ]}
        markup = keyboard(data)
        callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
        self.assertIn("pulse_form:choice:55:1:0", callbacks)
        self.assertIn("pulse_form:choice:55:1:1", callbacks)
        self.assertIn("pulse_form:skip:55:1", callbacks)
        self.assertIn("pulse_form:back:55:1", callbacks)
        self.assertIn("pulse_form:pause:55:1", callbacks)

    def test_submit_button_is_bound_to_preview_index(self):
        data = {"cycle_id": 55, "index": 1, "questions": [
            {"key": "done", "required": True, "choices": []},
        ]}
        callbacks = [
            button.callback_data
            for row in keyboard(data, preview=True).inline_keyboard
            for button in row
        ]
        self.assertIn("pulse_form:submit:55:1", callbacks)
