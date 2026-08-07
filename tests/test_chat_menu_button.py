from __future__ import annotations

import ast
import unittest
from pathlib import Path

from aiogram.types import MenuButtonCommands, MenuButtonDefault, MenuButtonWebApp, WebAppInfo

from app.webapp import _chat_menu_button, _menu_button_matches

APP_ROOT = Path(__file__).resolve().parents[1] / "app"
GUARDED_CALLS = {"set_chat_menu_button", "set_my_commands", "delete_my_commands"}
ALLOWED_FILE = APP_ROOT / "webapp.py"


class ChatMenuButtonTests(unittest.TestCase):
    """The persistent button next to the message input — see the
    docstring on _chat_menu_button() for why this exists as its own
    testable function rather than inline in lifespan()."""

    def test_opens_the_mini_app_directly_when_configured(self) -> None:
        button = _chat_menu_button("https://era-telegram-bot.onrender.com/app/")
        self.assertIsInstance(button, MenuButtonWebApp)
        self.assertEqual(button.web_app.url, "https://era-telegram-bot.onrender.com/app/")
        self.assertEqual(button.text, "Открыть ЭРА")

    def test_falls_back_to_commands_list_when_not_configured(self) -> None:
        # Mirrors Settings.effective_miniapp_url's own safety rule: stays
        # empty until MINIAPP_AUTH_SECRET is set, so this must not ship a
        # button that would open a broken Mini App.
        button = _chat_menu_button("")
        self.assertIsInstance(button, MenuButtonDefault)


class MenuButtonVerificationTests(unittest.TestCase):
    """Setting a menu button is fire-and-forget — this is the logic that
    turns Telegram's own getChatMenuButton response into a real pass/fail,
    used by lifespan() to log an ERROR (not just assume success) when
    Telegram doesn't actually store what was requested."""

    def test_matches_when_both_are_web_app_with_same_url(self) -> None:
        expected = MenuButtonWebApp(text="Открыть ЭРА", web_app=WebAppInfo(url="https://era.example/app/"))
        actual = MenuButtonWebApp(text="Открыть ЭРА", web_app=WebAppInfo(url="https://era.example/app/"))
        self.assertTrue(_menu_button_matches(expected, actual))

    def test_mismatch_when_urls_differ(self) -> None:
        expected = MenuButtonWebApp(text="Открыть ЭРА", web_app=WebAppInfo(url="https://era.example/app/"))
        actual = MenuButtonWebApp(text="Открыть ЭРА", web_app=WebAppInfo(url="https://old-host.example/app/"))
        self.assertFalse(_menu_button_matches(expected, actual))

    def test_mismatch_when_types_differ(self) -> None:
        expected = MenuButtonWebApp(text="Открыть ЭРА", web_app=WebAppInfo(url="https://era.example/app/"))
        actual = MenuButtonDefault()
        self.assertFalse(_menu_button_matches(expected, actual))

    def test_matches_when_both_are_default(self) -> None:
        self.assertTrue(_menu_button_matches(MenuButtonDefault(), MenuButtonDefault()))

    def test_default_matches_telegrams_own_commands_normalization(self) -> None:
        # Confirmed against real production behavior: sending `default`
        # (no explicit choice) makes Telegram report back `commands` for
        # a bot with registered commands — its own normalization, not a
        # failure to apply our setting. Discovered via /diag after PR21;
        # without this, every deploy would log a false ERROR forever.
        self.assertTrue(_menu_button_matches(MenuButtonDefault(), MenuButtonCommands()))

    def test_web_app_expected_but_default_returned_is_still_a_real_mismatch(self) -> None:
        expected = MenuButtonWebApp(text="Открыть ЭРА", web_app=WebAppInfo(url="https://era.example/app/"))
        self.assertFalse(_menu_button_matches(expected, MenuButtonCommands()))


class SingleSourceOfTruthTests(unittest.TestCase):
    """Item 4 of the live-config investigation: confirms, by actually
    parsing every .py file under app/ (not just trusting a one-time grep),
    that no handler anywhere re-configures the chat menu button or bot
    commands after lifespan() sets them — a second call site would win or
    race depending on execution order and silently undo this fix."""

    def test_no_other_file_calls_menu_or_command_setters(self) -> None:
        offending: list[str] = []
        for path in APP_ROOT.rglob("*.py"):
            if path == ALLOWED_FILE:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and node.attr in GUARDED_CALLS:
                    offending.append(f"{path.relative_to(APP_ROOT.parent)}: {node.attr}")
        self.assertEqual(offending, [])


if __name__ == "__main__":
    unittest.main()
