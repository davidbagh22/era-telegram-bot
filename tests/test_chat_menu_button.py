from __future__ import annotations

import unittest

from aiogram.types import MenuButtonDefault, MenuButtonWebApp

from app.webapp import _chat_menu_button


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


if __name__ == "__main__":
    unittest.main()
