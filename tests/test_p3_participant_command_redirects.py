"""Regression tests for participant compatibility commands.

Legacy typed commands stay live, but they now open the exact Mini App section
through Telegram-safe query routes rather than fragment-only URLs.
"""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit

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

    def assert_route(self, message: SimpleNamespace, route: str) -> None:
        url = message.answer.call_args.kwargs["reply_markup"].inline_keyboard[0][0].web_app.url
        parsed = urlsplit(url)
        self.assertEqual(parsed.fragment, "")
        self.assertEqual(parse_qs(parsed.query).get("eraPath"), [route])

    async def test_profile_redirects_to_profile_screen(self) -> None:
        message = await self._run(commands_ready.profile_command, _approved_user())
        (text,), _ = message.answer.call_args
        self.assertEqual(text, texts.PROFILE_MOVED)
        self.assert_route(message, "profile")

    async def test_data_redirects_to_profile_screen(self) -> None:
        message = await self._run(commands_ready.data_command, _approved_user())
        (text,), _ = message.answer.call_args
        self.assertEqual(text, texts.PROFILE_MOVED)
        self.assert_route(message, "profile")

    async def test_points_redirects_to_profile_screen(self) -> None:
        message = await self._run(commands_ready.points_command, _approved_user())
        (text,), _ = message.answer.call_args
        self.assertEqual(text, texts.PROFILE_MOVED)
        self.assert_route(message, "profile")

    async def test_events_redirects_to_events_screen(self) -> None:
        message = await self._run(commands_ready.events_command, _approved_user())
        (text,), _ = message.answer.call_args
        self.assertEqual(text, texts.EVENTS_MOVED)
        self.assert_route(message, "events")

    async def test_opportunities_redirects_to_opportunities_screen(self) -> None:
        message = await self._run(commands_ready.opportunities_command, _approved_user())
        (text,), _ = message.answer.call_args
        self.assertEqual(text, texts.OPPORTUNITIES_MOVED)
        self.assert_route(message, "opportunities")

    async def test_pending_applicant_still_blocked_not_redirected(self) -> None:
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
