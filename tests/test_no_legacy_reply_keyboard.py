"""Regression guard for ReplyKeyboardMarkup usage.

Persistent Telegram reply keyboards are retired everywhere. Participant
navigation lives in Mini App/contextual inline buttons; the general group chat
uses one pinned FAQ whose buttons open private bot deep links. faq.py may only
construct ReplyKeyboardRemove to clear clients that cached the historical dock.
"""

from __future__ import annotations

import unittest
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent / "app"


def _matching_files(needle: str) -> list[str]:
    hits = []
    for path in APP_ROOT.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if needle in text:
            hits.append(str(path.relative_to(APP_ROOT.parent)))
    return sorted(hits)


class NoLegacyReplyKeyboardTests(unittest.TestCase):
    def test_reply_keyboard_markup_is_gone(self) -> None:
        hits = _matching_files("ReplyKeyboardMarkup(")
        self.assertEqual(hits, [], f"Unexpected ReplyKeyboardMarkup construction in: {hits}")

    def test_resize_keyboard_is_gone(self) -> None:
        hits = _matching_files("resize_keyboard")
        self.assertEqual(hits, [], f"Unexpected resize_keyboard usage in: {hits}")

    def test_is_persistent_is_gone(self) -> None:
        hits = _matching_files("is_persistent")
        self.assertEqual(hits, [], f"Unexpected is_persistent usage in: {hits}")

    def test_no_one_time_keyboard_flag(self) -> None:
        hits = _matching_files("one_time_keyboard")
        self.assertEqual(hits, [], f"Found one_time_keyboard usage in: {hits}")

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
