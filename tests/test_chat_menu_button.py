from __future__ import annotations

import ast
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from pathlib import Path

from aiogram.types import MenuButtonCommands, MenuButtonDefault, MenuButtonWebApp, WebAppInfo

from app.webapp import _chat_menu_button, _menu_button_matches, _set_and_verify_menu_button

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


class MenuButtonReadBackTests(unittest.IsolatedAsyncioTestCase):
    async def test_stale_read_back_is_retried_without_rewriting_configuration(self):
        old = _chat_menu_button("https://era.example/previous-app/")
        current = _chat_menu_button("https://era.example/app/")
        bot = SimpleNamespace(set_chat_menu_button=AsyncMock(), get_chat_menu_button=AsyncMock(side_effect=[old, current]))
        with patch("app.webapp.asyncio.sleep", new=AsyncMock()):
            actual, verified = await _set_and_verify_menu_button(bot, current)
        self.assertTrue(verified)
        self.assertEqual(actual.web_app.url, current.web_app.url)
        bot.set_chat_menu_button.assert_awaited_once()

    async def test_persistent_mismatch_is_still_reported(self):
        current = _chat_menu_button("https://era.example/app/")
        bot = SimpleNamespace(set_chat_menu_button=AsyncMock(), get_chat_menu_button=AsyncMock(return_value=MenuButtonDefault()))
        with patch("app.webapp.asyncio.sleep", new=AsyncMock()):
            _, verified = await _set_and_verify_menu_button(bot, current)
        self.assertFalse(verified)
        self.assertEqual(bot.get_chat_menu_button.await_count, 3)


class SingleSourceOfTruthTests(unittest.TestCase):
    """Item 4 of the live-config investigation: confirms, by actually
    parsing every .py file under app/ (not just trusting a one-time grep),
    that no handler anywhere re-configures the chat menu button or bot
    commands after lifespan() sets them — a second call site would win or
    race depending on execution order and silently undo this fix."""

    def test_no_other_file_calls_menu_or_command_setters(self) -> None:
        offending: list[str] = []
        for path in APP_ROOT.rglob("*.py"):
            if path == ALLOWED_FILE or path.name.startswith("commission_bot"):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and node.attr in GUARDED_CALLS:
                    offending.append(f"{path.relative_to(APP_ROOT.parent)}: {node.attr}")
        self.assertEqual(offending, [])


if __name__ == "__main__":
    unittest.main()


class MenuReadbackRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_stale_app_path_has_a_longer_bounded_recovery_window(self):
        old = _chat_menu_button('https://era.example/previous-app/')
        current = _chat_menu_button('https://era.example/app/')
        bot = SimpleNamespace(set_chat_menu_button=AsyncMock(), get_chat_menu_button=AsyncMock(side_effect=[old, old, old, current]))
        with patch('app.webapp.asyncio.sleep', new=AsyncMock()):
            actual, verified = await _set_and_verify_menu_button(bot, current)
        self.assertTrue(verified)
        self.assertEqual(actual.web_app.url, current.web_app.url)
        self.assertEqual(bot.get_chat_menu_button.await_count, 4)

    async def test_persistent_url_mismatch_stops_and_reports_a_safe_reason(self):
        from app.webapp import _menu_button_mismatch_reason
        old = _chat_menu_button('https://era.example/previous-app/')
        current = _chat_menu_button('https://era.example/app/')
        bot = SimpleNamespace(set_chat_menu_button=AsyncMock(), get_chat_menu_button=AsyncMock(return_value=old))
        with patch('app.webapp.asyncio.sleep', new=AsyncMock()):
            _, verified = await _set_and_verify_menu_button(bot, current)
        self.assertFalse(verified)
        self.assertEqual(bot.get_chat_menu_button.await_count, 6)
        self.assertEqual(_menu_button_mismatch_reason(current, old), 'path')
        other = _chat_menu_button('https://different.example/app/?secret=private')
        self.assertEqual(_menu_button_mismatch_reason(current, other), 'origin')


class MenuButtonTargetTests(unittest.IsolatedAsyncioTestCase):
    async def test_stale_build_marker_keeps_the_same_app_and_needs_no_retries(self):
        current = _chat_menu_button("https://era.example/app/?v=new")
        old = _chat_menu_button("https://era.example/app/?v=old")
        bot = SimpleNamespace(set_chat_menu_button=AsyncMock(), get_chat_menu_button=AsyncMock(return_value=old))
        with patch("app.webapp.asyncio.sleep", new=AsyncMock()) as sleep:
            actual, verified = await _set_and_verify_menu_button(bot, current)
        self.assertTrue(verified)
        self.assertIs(actual, old)
        bot.set_chat_menu_button.assert_awaited_once()
        bot.get_chat_menu_button.assert_awaited_once()
        sleep.assert_not_awaited()

    def test_only_the_release_marker_can_differ(self):
        expected = _chat_menu_button("https://era.example/app/?section=events&v=new&empty=#profile")
        for url in (
            "https://era.example/app/?section=events&v=old&empty=#profile",
            "https://era.example/app/?section=events&empty=#profile",
        ):
            with self.subTest(url=url):
                self.assertTrue(_menu_button_matches(expected, _chat_menu_button(url)))

    def test_meaningful_query_entries_cannot_change(self):
        expected = _chat_menu_button("https://era.example/app/?section=events&v=new&empty=#profile")
        for url in (
            "https://era.example/app/?section=admin&v=old&empty=#profile",
            "https://era.example/app/?section=events&v=old#profile",
            "https://era.example/app/?section=events&v=old&empty=&section=admin#profile",
            "https://era.example/app/?empty=&section=events&v=old#profile",
            "https://era.example/app/?section=events&v=old&empty=#other",
            "http://era.example/app/?section=events&v=old&empty=#profile",
        ):
            with self.subTest(url=url):
                self.assertFalse(_menu_button_matches(expected, _chat_menu_button(url)))

    def test_safe_diagnostics_cover_actual_target_differences(self):
        from app.webapp import _menu_button_mismatch_reason
        expected = _chat_menu_button("https://era.example/app/?v=new&section=events")
        self.assertEqual(
            _menu_button_mismatch_reason(expected, _chat_menu_button("https://era.example/app/?v=old&section=events")),
            "match",
        )
        self.assertEqual(
            _menu_button_mismatch_reason(expected, _chat_menu_button("https://era.example/app/?v=old&section=other")),
            "query_or_fragment",
        )
