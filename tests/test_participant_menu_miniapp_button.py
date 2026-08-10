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

    def test_fallback_menu_used_only_when_miniapp_is_unconfigured(self) -> None:
        # PR 36 (Bot/Mini App role split): when the Mini App is configured,
        # main_menu() deliberately stops showing the old bot-side
        # "👤 Личный кабинет"/"📅 Афиша"/"✅ Задачи"/"⚙️ Панель" menu tree —
        # those are now Mini App-only surfaces. The old buttons only exist
        # as a fallback for environments without a configured Mini App
        # (e.g. local dev), so parity between the two states is no longer
        # expected or desired.
        without_miniapp = _button_texts(main_menu("https://t.me/era"))
        with_miniapp = _button_texts(
            main_menu("https://t.me/era", miniapp_url="https://era-app.example/")
        )
        self.assertIn("👤 Личный кабинет", without_miniapp)
        self.assertNotIn("👤 Личный кабинет", with_miniapp)

    def test_miniapp_menu_has_the_four_gateway_buttons(self) -> None:
        markup = main_menu(
            "https://t.me/era", privileged=True, admin=True, miniapp_url="https://era-app.example/"
        )
        texts = _button_texts(markup)
        self.assertEqual(
            texts,
            ["🔥 Открыть ЭРА", "📅 Ближайшее", "✅ Мои задачи", "⭐ Возможности", "💬 Связь"],
        )

    def test_quick_access_buttons_deep_link_into_the_right_miniapp_tab(self) -> None:
        markup = main_menu("https://t.me/era", miniapp_url="https://era-app.example")
        buttons = {button.text: button for row in markup.keyboard for button in row}
        self.assertEqual(buttons["🔥 Открыть ЭРА"].web_app.url, "https://era-app.example")
        self.assertEqual(buttons["📅 Ближайшее"].web_app.url, "https://era-app.example/#/events")
        self.assertEqual(buttons["✅ Мои задачи"].web_app.url, "https://era-app.example/#/tasks")
        self.assertEqual(
            buttons["⭐ Возможности"].web_app.url, "https://era-app.example/#/opportunities"
        )

    def test_panel_button_no_longer_shown_when_miniapp_is_configured(self) -> None:
        markup = main_menu(
            "https://t.me/era", privileged=True, admin=True, miniapp_url="https://era-app.example/"
        )
        self.assertNotIn("⚙️ Панель", _button_texts(markup))


if __name__ == "__main__":
    unittest.main()
