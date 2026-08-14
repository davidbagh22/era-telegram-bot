"""Regression tests for the role-aware Navigation bot message.

The bot is intentionally a gateway, not a second application surface. Each
role gets the same structured participant map plus one explicit workspace
entry when appropriate.
"""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit

from app.handlers.participant import navigation
from app.utils import texts
from app.utils.constants import ApplicationStatus


def _participant_user() -> SimpleNamespace:
    return SimpleNamespace(
        role="participant",
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
        permission_grants=[],
        application_status=ApplicationStatus.APPROVED,
    )


def _admin_user() -> SimpleNamespace:
    return SimpleNamespace(
        role="admin",
        is_blocked=False,
        is_archived=False,
        permission_grants=[],
        application_status=ApplicationStatus.APPROVED,
    )


def _pending_user() -> SimpleNamespace:
    return SimpleNamespace(
        role="participant",
        is_blocked=False,
        is_archived=False,
        permission_grants=[],
        application_status=ApplicationStatus.PENDING,
    )


def _settings(miniapp_url: str = "https://era-app.example/") -> SimpleNamespace:
    return SimpleNamespace(effective_miniapp_url=miniapp_url)


def _call() -> SimpleNamespace:
    return SimpleNamespace(answer=AsyncMock(), message=SimpleNamespace(answer=AsyncMock()))


class NavGuideCallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_participant_gets_the_participant_guide(self) -> None:
        call = _call()
        await navigation.nav_guide_callback(call, _participant_user(), _settings())
        call.answer.assert_awaited_once()
        (text,), kwargs = call.message.answer.call_args
        self.assertEqual(text, navigation.NAVIGATION_PARTICIPANT)
        self.assertIn("💡 <b>Проекты</b>", text)
        self.assertIn("💬 Связь", text)
        buttons = {b.text for row in kwargs["reply_markup"].inline_keyboard for b in row}
        self.assertNotIn("⚙️ Режим администратора", buttons)
        self.assertNotIn("🧭 Режим лидера", buttons)

    async def test_leader_gets_the_leader_guide_with_workspace_row(self) -> None:
        call = _call()
        await navigation.nav_guide_callback(call, _leader_user(), _settings())
        (text,), kwargs = call.message.answer.call_args
        self.assertEqual(text, navigation.NAVIGATION_LEADER)
        buttons = {b.text: b for row in kwargs["reply_markup"].inline_keyboard for b in row}
        self.assertIn("🧭 Режим лидера", buttons)
        route = parse_qs(urlsplit(buttons["🧭 Режим лидера"].web_app.url).query)
        self.assertEqual(route.get("eraPath"), ["leader"])

    async def test_admin_gets_the_admin_guide_with_workspace_row(self) -> None:
        call = _call()
        await navigation.nav_guide_callback(call, _admin_user(), _settings())
        (text,), kwargs = call.message.answer.call_args
        self.assertEqual(text, navigation.NAVIGATION_ADMIN)
        buttons = {b.text: b for row in kwargs["reply_markup"].inline_keyboard for b in row}
        self.assertIn("⚙️ Режим администратора", buttons)
        route = parse_qs(urlsplit(buttons["⚙️ Режим администратора"].web_app.url).query)
        self.assertEqual(route.get("eraPath"), ["admin"])

    async def test_pending_user_sees_application_pending_not_the_guide(self) -> None:
        call = _call()
        await navigation.nav_guide_callback(call, _pending_user(), _settings())
        (text,), kwargs = call.message.answer.call_args
        self.assertEqual(text, texts.APPLICATION_PENDING)
        self.assertNotIn("reply_markup", kwargs)

    async def test_none_user_is_treated_as_not_approved(self) -> None:
        call = _call()
        await navigation.nav_guide_callback(call, None, _settings())
        (text,), _ = call.message.answer.call_args
        self.assertEqual(text, texts.APPLICATION_PENDING)


if __name__ == "__main__":
    unittest.main()
