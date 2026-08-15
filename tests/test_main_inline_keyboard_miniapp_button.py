from __future__ import annotations

import unittest
from urllib.parse import parse_qs, urlsplit

from app.keyboards.participant import main_inline_keyboard, navigation_guide_keyboard


def _button_texts(markup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


def _route(button) -> str | None:
    if button.web_app is None:
        return None
    parsed = urlsplit(button.web_app.url)
    if parsed.fragment:
        raise AssertionError(f"external Telegram WebApp URL must not depend on fragment: {button.web_app.url}")
    values = parse_qs(parsed.query).get("eraPath")
    return values[0] if values else None


class MainInlineKeyboardMiniAppButtonTests(unittest.TestCase):
    """The bot's compact gateway must open exact Mini App destinations."""

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

    def test_panel_row_no_longer_shown_when_miniapp_is_configured(self) -> None:
        markup = main_inline_keyboard(admin=True, miniapp_url="https://era-app.example/")
        self.assertNotIn("⚙️ Панель", _button_texts(markup))

    def test_fallback_menu_used_only_when_miniapp_is_unconfigured(self) -> None:
        without_miniapp = _button_texts(main_inline_keyboard())
        with_miniapp = _button_texts(main_inline_keyboard(miniapp_url="https://era-app.example/"))
        self.assertIn("👤 Личный кабинет", without_miniapp)
        self.assertNotIn("👤 Личный кабинет", with_miniapp)

    def test_miniapp_menu_has_the_three_gateway_buttons(self) -> None:
        markup = main_inline_keyboard(
            privileged=True, admin=True, miniapp_url="https://era-app.example/"
        )
        self.assertEqual(
            _button_texts(markup),
            ["🔥 Открыть ЭРА", "🧭 Навигация", "💬 Связь"],
        )

    def test_navigation_button_is_a_callback_not_a_web_app_button(self) -> None:
        markup = main_inline_keyboard(miniapp_url="https://era-app.example")
        button = next(
            button
            for row in markup.inline_keyboard
            for button in row
            if button.text == "🧭 Навигация"
        )
        self.assertEqual(button.callback_data, "nav:guide")
        self.assertIsNone(button.web_app)

    def test_navigation_guide_keyboard_deep_links_into_the_right_miniapp_screens(self) -> None:
        markup = navigation_guide_keyboard("https://era-app.example")
        buttons = {button.text: button for row in markup.inline_keyboard for button in row}
        self.assertEqual(_route(buttons["Проекты"]), "projects")
        self.assertEqual(_route(buttons["События"]), "events")
        self.assertEqual(_route(buttons["Сообщество"]), "community")
        self.assertEqual(_route(buttons["Профиль"]), "profile")
        self.assertEqual(_route(buttons["Мои задачи"]), "tasks")
        self.assertEqual(_route(buttons["Возможности"]), "opportunities")
        self.assertNotIn("⚙️ Режим администратора", buttons)
        self.assertNotIn("🧭 Режим лидера", buttons)

    def test_navigation_guide_keyboard_adds_workspace_row_for_admin(self) -> None:
        markup = navigation_guide_keyboard("https://era-app.example", admin=True)
        buttons = {button.text: button for row in markup.inline_keyboard for button in row}
        self.assertIn("⚙️ Режим администратора", buttons)
        self.assertEqual(_route(buttons["⚙️ Режим администратора"]), "admin")

    def test_navigation_guide_keyboard_adds_workspace_row_for_leader(self) -> None:
        markup = navigation_guide_keyboard("https://era-app.example", privileged=True)
        buttons = {button.text: button for row in markup.inline_keyboard for button in row}
        self.assertIn("🧭 Режим лидера", buttons)
        self.assertEqual(_route(buttons["🧭 Режим лидера"]), "leader")

    def test_plain_participant_never_sees_the_panel_button(self) -> None:
        without_miniapp = _button_texts(main_inline_keyboard())
        with_miniapp = _button_texts(main_inline_keyboard(miniapp_url="https://era-app.example/"))
        self.assertNotIn("⚙️ Панель", without_miniapp)
        self.assertNotIn("⚙️ Панель", with_miniapp)

    def test_admin_menu_stays_compact_when_miniapp_is_configured(self) -> None:
        admin_markup = _button_texts(
            main_inline_keyboard(admin=True, miniapp_url="https://era-app.example/")
        )
        participant_markup = _button_texts(main_inline_keyboard(miniapp_url="https://era-app.example/"))
        self.assertEqual(admin_markup, participant_markup)


if __name__ == "__main__":
    unittest.main()
