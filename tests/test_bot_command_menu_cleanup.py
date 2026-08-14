"""Regression tests for the 2026-08 bot command-menu cleanup ToR: the
Telegram "/" autocomplete list must be down to /start, /navigation,
/contact for everyone (+/version, admin-only, purely diagnostic) --
/profile, /data, /events, /tasks, /opportunities, /points, /help must
not be advertised, even though each still has a live compatibility
redirect for anyone who types the old command by hand.
"""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.handlers.participant import about, commands_ready, navigation
from app.utils import texts
from app.utils.constants import ApplicationStatus
from app.webapp import ADMIN_COMMANDS, USER_COMMANDS


def _user() -> SimpleNamespace:
    return SimpleNamespace(
        application_status=ApplicationStatus.APPROVED,
        is_blocked=False,
        is_archived=False,
        role="participant",
        permission_grants=[],
    )


def _settings(miniapp_url: str = "https://era-app.example/") -> SimpleNamespace:
    return SimpleNamespace(effective_miniapp_url=miniapp_url)


def _message() -> SimpleNamespace:
    return SimpleNamespace(answer=AsyncMock())


class CommandMenuShapeTests(unittest.TestCase):
    def test_user_commands_are_exactly_three(self) -> None:
        self.assertEqual(
            [c.command for c in USER_COMMANDS], ["start", "navigation", "contact"]
        )

    def test_removed_commands_are_not_advertised(self) -> None:
        advertised = {c.command for c in USER_COMMANDS}
        for removed in ("profile", "data", "events", "tasks", "opportunities", "points", "help"):
            self.assertNotIn(removed, advertised)

    def test_admin_commands_add_only_hidden_version(self) -> None:
        self.assertEqual(
            [c.command for c in ADMIN_COMMANDS],
            ["start", "navigation", "contact", "version"],
        )
        # No legacy admin panel commands leak into the admin scope either.
        admin_advertised = {c.command for c in ADMIN_COMMANDS}
        self.assertNotIn("panel", admin_advertised)
        self.assertNotIn("admin", admin_advertised)


class RemovedCommandsStillRedirectTests(unittest.IsolatedAsyncioTestCase):
    """Not advertised != broken: anyone who still types the old command
    by hand gets a "this lives in the app now" redirect, never the old
    bot-native menu."""

    async def test_tasks_command_redirects_to_the_miniapp_not_the_old_task_menu(self) -> None:
        message = _message()
        state = SimpleNamespace(clear=AsyncMock())
        await commands_ready.tasks_command(message, _user(), _settings(), state)
        (text,), kwargs = message.answer.call_args
        self.assertEqual(text, texts.TASKS_MOVED)
        button = kwargs["reply_markup"].inline_keyboard[0][0]
        self.assertIsNotNone(button.web_app)
        self.assertIn("/#/tasks", button.web_app.url)

    async def test_help_command_shows_the_navigation_guide_not_the_old_about_menu(self) -> None:
        message = _message()
        state = SimpleNamespace(clear=AsyncMock())
        await commands_ready.help_command(message, _user(), _settings(), state)
        (text,), kwargs = message.answer.call_args
        self.assertEqual(text, texts.NAVIGATION_GUIDE_PARTICIPANT)
        buttons = [b for row in kwargs["reply_markup"].inline_keyboard for b in row]
        self.assertTrue(all(b.callback_data != "cabinet:open" for b in buttons))

    async def test_navigation_command_shows_the_same_guide_as_the_button(self) -> None:
        message = _message()
        state = SimpleNamespace(clear=AsyncMock())
        await navigation.navigation_command(message, _user(), _settings(), state)
        state.clear.assert_awaited_once()
        (text,), kwargs = message.answer.call_args
        self.assertEqual(text, texts.NAVIGATION_GUIDE_PARTICIPANT)
        self.assertIsNotNone(kwargs["reply_markup"])

    async def test_about_command_no_longer_shows_the_legacy_menu(self) -> None:
        message = _message()
        state = SimpleNamespace(clear=AsyncMock())
        await about.about_button(message, _user(), _settings(), state)
        (text,), kwargs = message.answer.call_args
        self.assertEqual(text, about.ABOUT_TEXT)
        markup = kwargs["reply_markup"]
        buttons = [b for row in markup.inline_keyboard for b in row]
        self.assertTrue(all(b.web_app is not None for b in buttons))
        self.assertTrue(all(b.callback_data is None for b in buttons))


if __name__ == "__main__":
    unittest.main()
