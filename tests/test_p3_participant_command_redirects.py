"""Regression tests for P3 of the 2026-08 master spec: /profile, /data,
/events, /opportunities, and /points are advertised in the bot's public
autocomplete menu and used to each open a bot-native duplicate of a Mini
App screen. They now redirect to the specific Mini App screen instead
(deep-linked, not just the app's home) — kept live, not deleted.
/menu, /contact, and /help are explicitly unaffected and not covered here.
"""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.handlers.participant import commands_ready
from app.utils import texts
from app.utils.constants import ApplicationStatus


def _approved_user() -> SimpleNamespace:
    return SimpleNamespace(
        application_status=ApplicationStatus.APPROVED, is_blocked=False, is_archived=False
    )


def _pending_user() -> SimpleNamespace:
    return SimpleNamespace(
        application_status=ApplicationStatus.PENDING, is_blocked=False, is_archived=False
    )


def _settings() -> SimpleNamespace:
    return SimpleNamespace(effective_miniapp_url="https://era-app.example/")


class ParticipantCommandRedirectTests(unittest.IsolatedAsyncioTestCase):
    async def _run(self, handler, user):
        message = SimpleNamespace(answer=AsyncMock())
        state = SimpleNamespace(clear=AsyncMock())
        await handler(message, user, _settings(), state)
        return message

    async def test_profile_redirects_to_profile_screen(self) -> None:
        message = await self._run(commands_ready.profile_command, _approved_user())
        (text,), kwargs = message.answer.call_args
        self.assertEqual(text, texts.PROFILE_MOVED)
        self.assertEqual(kwargs["reply_markup"].inline_keyboard[0][0].web_app.url, "https://era-app.example/#/profile")

    async def test_data_redirects_to_profile_screen(self) -> None:
        message = await self._run(commands_ready.data_command, _approved_user())
        (text,), kwargs = message.answer.call_args
        self.assertEqual(text, texts.PROFILE_MOVED)
        self.assertEqual(kwargs["reply_markup"].inline_keyboard[0][0].web_app.url, "https://era-app.example/#/profile")

    async def test_points_redirects_to_profile_screen(self) -> None:
        message = await self._run(commands_ready.points_command, _approved_user())
        (text,), kwargs = message.answer.call_args
        self.assertEqual(text, texts.PROFILE_MOVED)
        self.assertEqual(kwargs["reply_markup"].inline_keyboard[0][0].web_app.url, "https://era-app.example/#/profile")

    async def test_events_redirects_to_events_screen(self) -> None:
        message = await self._run(commands_ready.events_command, _approved_user())
        (text,), kwargs = message.answer.call_args
        self.assertEqual(text, texts.EVENTS_MOVED)
        self.assertEqual(kwargs["reply_markup"].inline_keyboard[0][0].web_app.url, "https://era-app.example/#/events")

    async def test_opportunities_redirects_to_opportunities_screen(self) -> None:
        message = await self._run(commands_ready.opportunities_command, _approved_user())
        (text,), kwargs = message.answer.call_args
        self.assertEqual(text, texts.OPPORTUNITIES_MOVED)
        self.assertEqual(
            kwargs["reply_markup"].inline_keyboard[0][0].web_app.url, "https://era-app.example/#/opportunities"
        )

    async def test_pending_applicant_still_blocked_not_redirected(self) -> None:
        # A not-yet-approved participant must still see the usual
        # "your application is pending" message, not the Mini App redirect
        # — matches the original handlers' behavior before this change.
        for handler in (
            commands_ready.profile_command,
            commands_ready.data_command,
            commands_ready.events_command,
            commands_ready.opportunities_command,
            commands_ready.points_command,
        ):
            message = await self._run(handler, _pending_user())
            (text,), kwargs = message.answer.call_args
            self.assertEqual(text, texts.APPLICATION_PENDING, f"{handler.__name__} did not gate on approval")
            self.assertNotIn("reply_markup", kwargs)

    async def test_redirect_degrades_gracefully_when_miniapp_unconfigured(self) -> None:
        message = SimpleNamespace(answer=AsyncMock())
        state = SimpleNamespace(clear=AsyncMock())
        await commands_ready.profile_command(
            message, _approved_user(), SimpleNamespace(effective_miniapp_url=""), state
        )
        _, kwargs = message.answer.call_args
        self.assertIsNone(kwargs["reply_markup"])


if __name__ == "__main__":
    unittest.main()
