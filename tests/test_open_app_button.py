from __future__ import annotations

import unittest

from app.keyboards.participant import open_app_button


class OpenAppButtonTests(unittest.TestCase):
    """Shared helper used by admin notifications that used to carry
    admin: callback buttons (approve/reject/etc.) — see
    docs/ERA_PLATFORM_PROGRESS.md's PR 30 section. Review now happens in
    the Mini App, not in a bot chat flow, so these notifications only
    need a WebApp button pointing there."""

    def test_returns_none_when_url_is_unset(self) -> None:
        self.assertIsNone(open_app_button(""))

    def test_returns_a_single_web_app_button(self) -> None:
        markup = open_app_button("https://era-app.example/")
        self.assertIsNotNone(markup)
        self.assertEqual(len(markup.inline_keyboard), 1)
        self.assertEqual(len(markup.inline_keyboard[0]), 1)
        button = markup.inline_keyboard[0][0]
        self.assertIsNotNone(button.web_app)
        self.assertEqual(button.web_app.url, "https://era-app.example/")
        self.assertIsNone(button.callback_data)

    def test_default_label(self) -> None:
        markup = open_app_button("https://era-app.example/")
        self.assertEqual(markup.inline_keyboard[0][0].text, "Открыть в приложении ЭРА")

    def test_custom_label(self) -> None:
        markup = open_app_button("https://era-app.example/", label="Открыть заявку")
        self.assertEqual(markup.inline_keyboard[0][0].text, "Открыть заявку")


if __name__ == "__main__":
    unittest.main()
