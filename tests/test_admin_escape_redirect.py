"""Regression test for the 2026-08 bot-cleanup ToR ("/panel и /admin не
должны запускать старые меню, FSM, callbacks и admin flows"): /cancel and
the escape-text/escape-callback shortcuts (Отменить/Назад/etc., and the
admin:panel/admin:task:cancel callbacks) used to clear the FSM and then
reopen admin_panel_keyboard() — the old bot-native 6-tile admin menu tree.
That was the last live entry point into it (docs/BOT_VS_MINIAPP_AUDIT.md's
compatibility redirect only covered the /panel and /admin commands
themselves). See app/handlers/admin/addons.py's _reset_admin_state.
"""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.handlers.admin import addons
from app.utils import texts


def _admin_user() -> SimpleNamespace:
    return SimpleNamespace(role="admin", is_blocked=False, permission_grants=[])


def _settings(miniapp_url: str = "https://era-app.example/") -> SimpleNamespace:
    return SimpleNamespace(effective_miniapp_url=miniapp_url, admin_ids=[])


def _message() -> SimpleNamespace:
    return SimpleNamespace(answer=AsyncMock(), from_user=SimpleNamespace(id=1))


def _call() -> SimpleNamespace:
    return SimpleNamespace(
        answer=AsyncMock(),
        message=SimpleNamespace(answer=AsyncMock()),
        from_user=SimpleNamespace(id=1),
    )


class AdminEscapeRedirectTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancel_command_redirects_instead_of_reopening_menu_tree(self) -> None:
        message = _message()
        state = SimpleNamespace(clear=AsyncMock())
        await addons.admin_cancel_command(message, _admin_user(), _settings(), state)
        state.clear.assert_awaited_once()
        (text,), kwargs = message.answer.call_args
        self.assertEqual(text, texts.ADMIN_PANEL_MOVED)
        markup = kwargs["reply_markup"]
        self.assertIsNotNone(markup)
        buttons = [b for row in markup.inline_keyboard for b in row]
        self.assertTrue(all(b.web_app is not None for b in buttons))
        self.assertTrue(all(b.callback_data is None for b in buttons))

    async def test_escape_text_redirects_instead_of_reopening_menu_tree(self) -> None:
        message = _message()
        state = SimpleNamespace(clear=AsyncMock())
        await addons.admin_escape_text(message, _admin_user(), _settings(), state)
        state.clear.assert_awaited_once()
        (text,), _ = message.answer.call_args
        self.assertEqual(text, texts.ADMIN_PANEL_MOVED)

    async def test_escape_callback_redirects_instead_of_reopening_menu_tree(self) -> None:
        call = _call()
        state = SimpleNamespace(clear=AsyncMock())
        await addons.admin_escape_callback(call, _admin_user(), _settings(), state)
        state.clear.assert_awaited_once()
        (text,), _ = call.message.answer.call_args
        self.assertEqual(text, texts.ADMIN_PANEL_MOVED)

    async def test_redirect_degrades_gracefully_when_miniapp_unconfigured(self) -> None:
        message = _message()
        state = SimpleNamespace(clear=AsyncMock())
        await addons.admin_cancel_command(message, _admin_user(), _settings(miniapp_url=""), state)
        _, kwargs = message.answer.call_args
        self.assertIsNone(kwargs["reply_markup"])


if __name__ == "__main__":
    unittest.main()
