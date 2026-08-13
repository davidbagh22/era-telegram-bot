"""show_home() (app/handlers/start.py) is what a returning approved user's
/start actually renders (after emergency.rescue_start delegates to it in
production — see test_fsm_global_recovery.py). This closes the loop on the
scenario from the request: an approved user's /start reply must carry the
WebApp "🔥 Открыть ЭРА" entry point, never the old persistent
ReplyKeyboardMarkup main menu (which no longer exists in the codebase at
all — see tests/test_no_legacy_reply_keyboard.py)."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup

from app.handlers.start import show_home
from app.utils.constants import ApplicationStatus, Role


class FakeMessage:
    def __init__(self) -> None:
        self.answers: list[tuple[str, dict]] = []

    async def answer(self, text, **kwargs):
        self.answers.append((text, kwargs))


def _approved_user(role: str = Role.PARTICIPANT) -> SimpleNamespace:
    return SimpleNamespace(
        role=role,
        application_status=ApplicationStatus.APPROVED,
        is_blocked=False,
        is_archived=False,
        permission_grants=[],
    )


class ShowHomeNoLegacyKeyboardTests(unittest.IsolatedAsyncioTestCase):
    async def test_reply_markup_is_inline_not_a_persistent_reply_keyboard(self) -> None:
        message = FakeMessage()
        settings = SimpleNamespace(
            era_channel_url="https://t.me/example",
            effective_miniapp_url="https://era-app.example/",
        )

        await show_home(message, _approved_user(), settings)

        self.assertEqual(len(message.answers), 1)
        _, kwargs = message.answers[0]
        markup = kwargs["reply_markup"]
        self.assertIsInstance(markup, InlineKeyboardMarkup)
        self.assertNotIsInstance(markup, ReplyKeyboardMarkup)

    async def test_reply_carries_the_webapp_entry_point(self) -> None:
        message = FakeMessage()
        settings = SimpleNamespace(
            era_channel_url="https://t.me/example",
            effective_miniapp_url="https://era-app.example/",
        )

        await show_home(message, _approved_user(), settings)

        markup = message.answers[0][1]["reply_markup"]
        buttons = [button for row in markup.inline_keyboard for button in row]
        entry_button = next((b for b in buttons if b.text == "🔥 Открыть ЭРА"), None)
        self.assertIsNotNone(entry_button, "🔥 Открыть ЭРА missing from /start's reply")
        self.assertEqual(entry_button.web_app.url, settings.effective_miniapp_url)


if __name__ == "__main__":
    unittest.main()
