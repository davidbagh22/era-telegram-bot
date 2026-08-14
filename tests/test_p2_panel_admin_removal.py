"""Regression tests for the 2026-08 master spec's Bot/Mini App role split
(section 23): "/panel and /admin must be removed from the live bot for
real" — Admin Mode in the Mini App is now the only admin surface, and every
bot-native entry point into the old browse-menu tree (admin_panel_keyboard(),
admin_users_keyboard(), etc.) must show a compatibility redirect instead of
the tree itself. The commands are kept live (not deleted), so this pins the
*behavior change*, not just source text.

Also covers the P5 follow-up: /leader and the leader:panel callback got the
same compatibility-redirect treatment (they used to open the full bot-native
leader_panel_keyboard() tree, duplicating LeaderScreen in the Mini App).
"""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.handlers.admin import commands_ready, dashboard_block_a, management_ready
from app.handlers.leader import panel as leader_panel_module
from app.handlers.participant import navigation
from app.utils import texts
from app.utils.constants import ApplicationStatus


def _admin_user() -> SimpleNamespace:
    return SimpleNamespace(
        role="admin",
        is_blocked=False,
        is_archived=False,
        permission_grants=[],
        application_status=ApplicationStatus.APPROVED,
    )


def _leader_user() -> SimpleNamespace:
    return SimpleNamespace(
        role="leader",
        is_blocked=False,
        is_archived=False,
        application_status=ApplicationStatus.APPROVED,
    )


def _settings(miniapp_url: str = "https://era-app.example/") -> SimpleNamespace:
    return SimpleNamespace(admin_ids=[], effective_miniapp_url=miniapp_url)


class PanelAndAdminCommandsRedirectTests(unittest.IsolatedAsyncioTestCase):
    async def test_panel_command_redirects_instead_of_opening_menu_tree(self) -> None:
        message = SimpleNamespace(answer=AsyncMock(), from_user=SimpleNamespace(id=1))
        state = SimpleNamespace(clear=AsyncMock())
        await management_ready.panel_command(message, _admin_user(), _settings(), state)
        message.answer.assert_awaited_once()
        (text,), kwargs = message.answer.call_args
        self.assertEqual(text, texts.ADMIN_PANEL_MOVED)
        # Not the old browse-menu tree: no admin:menu:* callback buttons.
        markup = kwargs["reply_markup"]
        self.assertIsNotNone(markup)
        buttons = [b for row in markup.inline_keyboard for b in row]
        self.assertTrue(all(b.web_app is not None for b in buttons))

    async def test_admin_command_redirects_instead_of_opening_dashboard(self) -> None:
        message = SimpleNamespace(answer=AsyncMock(), from_user=SimpleNamespace(id=1))
        state = SimpleNamespace(clear=AsyncMock())
        await dashboard_block_a.admin_dashboard(message, _admin_user(), _settings(), state)
        message.answer.assert_awaited_once()
        (text,), _ = message.answer.call_args
        self.assertEqual(text, texts.ADMIN_PANEL_MOVED)

    async def test_admin_panel_callback_redirects_instead_of_reopening_dashboard(self) -> None:
        call = SimpleNamespace(
            answer=AsyncMock(),
            message=SimpleNamespace(answer=AsyncMock()),
            from_user=SimpleNamespace(id=1),
        )
        state = SimpleNamespace(clear=AsyncMock())
        await dashboard_block_a.admin_dashboard_callback(call, _admin_user(), _settings(), state)
        call.message.answer.assert_awaited_once()
        (text,), _ = call.message.answer.call_args
        self.assertEqual(text, texts.ADMIN_PANEL_MOVED)

    async def test_panel_button_and_callback_redirect_for_admins(self) -> None:
        message = SimpleNamespace(answer=AsyncMock())
        state = SimpleNamespace(clear=AsyncMock())
        await navigation.panel_button(message, _admin_user(), state, _settings())
        (text,), _ = message.answer.call_args
        self.assertEqual(text, texts.ADMIN_PANEL_MOVED)

        call = SimpleNamespace(answer=AsyncMock(), message=SimpleNamespace(answer=AsyncMock()))
        await navigation.panel_callback(call, _admin_user(), _settings())
        (text,), _ = call.message.answer.call_args
        self.assertEqual(text, texts.ADMIN_PANEL_MOVED)

    async def test_all_six_admin_shortcut_commands_redirect(self) -> None:
        handlers = [
            commands_ready.admin_users_command,
            commands_ready.admin_events_command,
            commands_ready.admin_projects_command,
            commands_ready.admin_partners_command,
            commands_ready.admin_tasks_command,
            commands_ready.admin_rights_command,
        ]
        for handler in handlers:
            message = SimpleNamespace(answer=AsyncMock(), from_user=SimpleNamespace(id=1))
            state = SimpleNamespace(clear=AsyncMock())
            await handler(message, _admin_user(), _settings(), state)
            message.answer.assert_awaited_once()
            (text,), _ = message.answer.call_args
            self.assertEqual(
                text, texts.ADMIN_PANEL_MOVED, f"{handler.__name__} did not redirect to the Mini App"
            )

    async def test_redirect_degrades_gracefully_when_miniapp_unconfigured(self) -> None:
        # open_app_button() returns None (no keyboard) rather than a broken
        # button when the Mini App isn't configured (e.g. local dev) —
        # matches the existing pattern already used for notifications.
        message = SimpleNamespace(answer=AsyncMock(), from_user=SimpleNamespace(id=1))
        state = SimpleNamespace(clear=AsyncMock())
        await management_ready.panel_command(message, _admin_user(), _settings(miniapp_url=""), state)
        _, kwargs = message.answer.call_args
        self.assertIsNone(kwargs["reply_markup"])


class LeaderPanelRedirectTests(unittest.IsolatedAsyncioTestCase):
    async def test_leader_command_redirects_instead_of_opening_menu_tree(self) -> None:
        message = SimpleNamespace(answer=AsyncMock())
        state = SimpleNamespace(clear=AsyncMock())
        await leader_panel_module.leader_command(message, _leader_user(), state, _settings())
        message.answer.assert_awaited_once()
        (text,), kwargs = message.answer.call_args
        self.assertEqual(text, texts.LEADER_PANEL_MOVED)
        # Not the old browse-menu tree: no leader:* callback buttons.
        markup = kwargs["reply_markup"]
        self.assertIsNotNone(markup)
        buttons = [b for row in markup.inline_keyboard for b in row]
        self.assertTrue(all(b.web_app is not None for b in buttons))

    async def test_leader_panel_callback_redirects_instead_of_reopening_menu(self) -> None:
        call = SimpleNamespace(answer=AsyncMock(), message=SimpleNamespace(answer=AsyncMock()))
        await leader_panel_module.leader_panel(call, _leader_user(), _settings())
        call.message.answer.assert_awaited_once()
        (text,), _ = call.message.answer.call_args
        self.assertEqual(text, texts.LEADER_PANEL_MOVED)

    async def test_redirect_degrades_gracefully_when_miniapp_unconfigured(self) -> None:
        message = SimpleNamespace(answer=AsyncMock())
        state = SimpleNamespace(clear=AsyncMock())
        await leader_panel_module.leader_command(
            message, _leader_user(), state, _settings(miniapp_url="")
        )
        _, kwargs = message.answer.call_args
        self.assertIsNone(kwargs["reply_markup"])


if __name__ == "__main__":
    unittest.main()
