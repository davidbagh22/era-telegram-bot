from __future__ import annotations

import unittest

from app.keyboards.participant import main_inline_keyboard


def _button_texts(markup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


class MainInlineKeyboardMiniAppButtonTests(unittest.TestCase):
    """main_menu() (the reply keyboard shown on /start) has had this
    button since the original 12-PR plan (see
    test_participant_menu_miniapp_button.py) — main_inline_keyboard() (the
    keyboard shown by /menu and "🧭 Главное меню" via _send_main_menu())
    never did, regardless of how many times main_menu() was fixed. Both
    keyboards claim to be "the main menu" from the user's perspective."""

    def test_no_miniapp_button_when_url_is_unset(self) -> None:
        markup = main_inline_keyboard()
        self.assertNotIn("🔥 Открыть ЭРА", _button_texts(markup))

    def test_miniapp_button_appears_when_url_is_configured(self) -> None:
        markup = main_inline_keyboard(miniapp_url="https://era-app.example/")
        self.assertIn("🔥 Открыть ЭРА", _button_texts(markup))

    def test_miniapp_button_is_a_real_web_app_button_not_a_callback(self) -> None:
        markup = main_inline_keyboard(miniapp_url="https://era-app.example/")
        button = next(
            button
            for row in markup.inline_keyboard
            for button in row
            if button.text == "🔥 Открыть ЭРА"
        )
        self.assertIsNotNone(button.web_app)
        self.assertEqual(button.web_app.url, "https://era-app.example/")
        self.assertIsNone(button.callback_data)

    def test_privileged_panel_row_still_appended_after_miniapp_button(self) -> None:
        markup = main_inline_keyboard(admin=True, miniapp_url="https://era-app.example/")
        self.assertIn("⚙️ Панель", _button_texts(markup))


if __name__ == "__main__":
    unittest.main()
