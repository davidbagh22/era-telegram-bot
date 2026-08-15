"""Regression guard for ReplyKeyboardMarkup usage.

The old participant/private-chat main menu must never return. The only deliberate
exception is the two-button persistent keyboard in app/keyboards/faq.py used by
the registered *general group chat* for `События` / `Мой профиль`. Telegram does
not support Web App KeyboardButton actions in groups, so that keyboard is a
small text-trigger dock whose messages are immediately removed and routed to a
private Mini App deep link by app.handlers.chat.
"""

from __future__ import annotations

import unittest
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent / "app"
GENERAL_CHAT_KEYBOARD_FILE = "app/keyboards/faq.py"


def _matching_files(needle: str) -> list[str]:
    hits = []
    for path in APP_ROOT.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if needle in text:
            hits.append(str(path.relative_to(APP_ROOT.parent)))
    return sorted(hits)


class NoLegacyReplyKeyboardTests(unittest.TestCase):
    def test_reply_keyboard_markup_is_only_general_chat_dock(self) -> None:
        hits = _matching_files("ReplyKeyboardMarkup(")
        self.assertEqual(
            hits,
            [GENERAL_CHAT_KEYBOARD_FILE],
            f"Unexpected ReplyKeyboardMarkup construction in: {hits}",
        )

    def test_resize_keyboard_is_only_general_chat_dock(self) -> None:
        hits = _matching_files("resize_keyboard")
        self.assertEqual(
            hits,
            [GENERAL_CHAT_KEYBOARD_FILE],
            f"Unexpected resize_keyboard usage in: {hits}",
        )

    def test_is_persistent_is_only_general_chat_dock(self) -> None:
        hits = _matching_files("is_persistent")
        self.assertEqual(
            hits,
            [GENERAL_CHAT_KEYBOARD_FILE],
            f"Unexpected is_persistent usage in: {hits}",
        )

    def test_no_one_time_keyboard_flag(self) -> None:
        hits = _matching_files("one_time_keyboard")
        self.assertEqual(hits, [], f"Found one_time_keyboard usage in: {hits}")

    def test_no_main_menu_function_left_behind(self) -> None:
        hits = _matching_files("def main_menu(")
        self.assertEqual(hits, [], f"Found def main_menu( in: {hits}")

    def test_participant_keyboard_never_uses_reply_markup(self) -> None:
        participant = (APP_ROOT / "keyboards" / "participant.py").read_text(encoding="utf-8")
        self.assertNotIn("ReplyKeyboardMarkup", participant)
        self.assertNotIn("is_persistent", participant)
        self.assertNotIn("resize_keyboard", participant)


if __name__ == "__main__":
    unittest.main()
