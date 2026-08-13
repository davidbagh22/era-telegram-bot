"""Permanent regression guard: no persistent ReplyKeyboardMarkup main menu
anywhere in production code, ever again.

main_menu() (app/keyboards/participant.py) used to build one and has been
removed entirely — see app/middlewares/legacy_keyboard_cleanup.py for the
one-time ReplyKeyboardRemove() migration for users who already have it
cached. This test source-scans app/ so a future PR can't quietly reintroduce
a persistent reply keyboard without this test failing first.
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
    return hits


class NoLegacyReplyKeyboardTests(unittest.TestCase):
    def test_no_reply_keyboard_markup_construction(self) -> None:
        hits = _matching_files("ReplyKeyboardMarkup(")
        self.assertEqual(hits, [], f"Found ReplyKeyboardMarkup( construction in: {hits}")

    def test_no_resize_keyboard_flag(self) -> None:
        # resize_keyboard is a ReplyKeyboardMarkup-only field; its presence
        # would mean a persistent keyboard came back somewhere.
        hits = _matching_files("resize_keyboard")
        self.assertEqual(hits, [], f"Found resize_keyboard usage in: {hits}")

    def test_no_is_persistent_flag(self) -> None:
        hits = _matching_files("is_persistent")
        self.assertEqual(hits, [], f"Found is_persistent usage in: {hits}")

    def test_no_one_time_keyboard_flag(self) -> None:
        hits = _matching_files("one_time_keyboard")
        self.assertEqual(hits, [], f"Found one_time_keyboard usage in: {hits}")

    def test_no_main_menu_function_left_behind(self) -> None:
        # The old function name itself — guards against someone quietly
        # re-adding a `def main_menu(...)` that returns a ReplyKeyboardMarkup
        # again under the same recognizable name.
        hits = _matching_files("def main_menu(")
        self.assertEqual(hits, [], f"Found def main_menu( in: {hits}")


if __name__ == "__main__":
    unittest.main()
