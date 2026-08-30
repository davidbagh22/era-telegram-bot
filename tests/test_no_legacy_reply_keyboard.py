"""Regression guard for ReplyKeyboardMarkup usage.

Persistent reply keyboards remain retired everywhere except the deliberately
small general-chat navigation dock in app/keyboards/faq.py. That dock contains
only «📅 Мероприятия» and «👤 Моя ЭРА» and routes presses privately.
"""

from __future__ import annotations

import unittest
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent / "app"
ALLOWED_REPLY_KEYBOARD_FILE = "app/keyboards/faq.py"


def _matching_files(needle: str) -> list[str]:
    hits = []
    for path in APP_ROOT.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if needle in text:
            hits.append(str(path.relative_to(APP_ROOT.parent)))
    return sorted(hits)


class NoLegacyReplyKeyboardTests(unittest.TestCase):
    def _assert_only_general_chat_dock(self, needle: str) -> None:
        hits = _matching_files(needle)
        self.assertEqual(hits, [ALLOWED_REPLY_KEYBOARD_FILE], f"Unexpected {needle} usage in: {hits}")

    def test_reply_keyboard_markup_exists_only_for_general_chat_dock(self) -> None:
        self._assert_only_general_chat_dock("ReplyKeyboardMarkup(")

    def test_resize_keyboard_exists_only_for_general_chat_dock(self) -> None:
        self._assert_only_general_chat_dock("resize_keyboard")

    def test_is_persistent_exists_only_for_general_chat_dock(self) -> None:
        self._assert_only_general_chat_dock("is_persistent")

    def test_one_time_keyboard_flag_exists_only_for_general_chat_dock(self) -> None:
        self._assert_only_general_chat_dock("one_time_keyboard")

    def test_no_main_menu_function_left_behind(self) -> None:
        hits = _matching_files("def main_menu(")
        self.assertEqual(hits, [], f"Found def main_menu( in: {hits}")

    def test_participant_keyboard_never_constructs_reply_markup(self) -> None:
        participant = (APP_ROOT / "keyboards" / "participant.py").read_text(encoding="utf-8")
        self.assertNotIn("ReplyKeyboardMarkup(", participant)
        self.assertNotIn("is_persistent=", participant)
        self.assertNotIn("resize_keyboard=", participant)


if __name__ == "__main__":
    unittest.main()
