from __future__ import annotations

import unittest

from app.keyboards.participant import main_menu


def _button_texts(markup) -> list[str]:
    return [button.text for row in markup.keyboard for button in row]


class MainMenuMiniAppButtonTests(unittest.TestCase):
    def test_no_miniapp_button_when_url_is_unset(self) -> None:
        markup = main_menu("https://t.me/era")
        self.assertNotIn("🔥 Открыть ЭРА", _button_texts(markup))

    def test_miniapp_button_appears_when_url_is_configured(self) -> None:
        markup = main_menu("https://t.me/era", miniapp_url="https://era-app.example/")
        texts = _button_texts(markup)
        self.assertIn("🔥 Открыть ЭРА", texts)

    def test_existing_buttons_are_unchanged(self) -> None:
        without_miniapp = _button_texts(main_menu("https://t.me/era"))
        with_miniapp = _button_texts(
            main_menu("https://t.me/era", miniapp_url="https://era-app.example/")
        )
        for label in without_miniapp:
            self.assertIn(label, with_miniapp)

    def test_privileged_and_admin_rows_still_appended_after_miniapp_button(self) -> None:
        markup = main_menu(
            "https://t.me/era", privileged=True, miniapp_url="https://era-app.example/"
        )
        self.assertIn("⚙️ Панель", _button_texts(markup))


if __name__ == "__main__":
    unittest.main()
