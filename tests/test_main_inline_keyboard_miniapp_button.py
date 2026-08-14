from __future__ import annotations

import unittest

from app.keyboards.participant import main_inline_keyboard, navigation_guide_keyboard


def _button_texts(markup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


class MainInlineKeyboardMiniAppButtonTests(unittest.TestCase):
    """main_inline_keyboard() is now the bot's one and only "main menu"
    surface — the old persistent ReplyKeyboardMarkup main_menu() it used
    to sit alongside (see test_participant_menu_miniapp_button.py, before
    it was removed and folded into this file) is gone entirely; Telegram
    clients that still have it cached get a one-time ReplyKeyboardRemove()
    via app/middlewares/legacy_keyboard_cleanup.py instead."""

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
        # PR 36 (Bot/Mini App role split): "⚙️ Панель" (a callback into the
        # bot's own app/handlers/admin/panel.py tree) is no longer
        # advertised once the Mini App is configured — 🔥 Открыть ЭРА
        # already routes an admin straight into Mini App Admin Mode (see
        # frontend/src/app/App.tsx's is_admin branch), so a second,
        # bot-side admin entry point would just be a duplicate UX.
        markup = main_inline_keyboard(admin=True, miniapp_url="https://era-app.example/")
        self.assertNotIn("⚙️ Панель", _button_texts(markup))

    def test_fallback_menu_used_only_when_miniapp_is_unconfigured(self) -> None:
        # The old bot-side "👤 Личный кабинет"/"📅 Афиша"/"✅ Задачи"/
        # "⚙️ Панель" menu tree only exists as a fallback for environments
        # without a configured Mini App (e.g. local dev) — parity between
        # the two states is not expected or desired once the Mini App is
        # configured.
        without_miniapp = _button_texts(main_inline_keyboard())
        with_miniapp = _button_texts(main_inline_keyboard(miniapp_url="https://era-app.example/"))
        self.assertIn("👤 Личный кабинет", without_miniapp)
        self.assertNotIn("👤 Личный кабинет", with_miniapp)

    def test_miniapp_menu_has_the_three_gateway_buttons(self) -> None:
        # 2026-08 redesign brief section 36: the old separate 📅
        # Ближайшее/✅ Мои задачи/⭐ Возможности quick-access buttons
        # collapsed into one 🧭 Навигация button — the bot explains and
        # links to the app instead of carrying a second, parallel set of
        # shortcuts into the same screens.
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
        self.assertEqual(buttons["Проекты"].web_app.url, "https://era-app.example/#/projects")
        self.assertEqual(buttons["События"].web_app.url, "https://era-app.example/#/events")
        self.assertEqual(buttons["Сообщество"].web_app.url, "https://era-app.example/#/community")
        self.assertEqual(buttons["Профиль"].web_app.url, "https://era-app.example/#/profile")
        self.assertEqual(buttons["Мои задачи"].web_app.url, "https://era-app.example/#/tasks")
        self.assertEqual(buttons["Возможности"].web_app.url, "https://era-app.example/#/opportunities")
        self.assertNotIn("⚙️ Режим администратора", buttons)
        self.assertNotIn("🧭 Режим лидера", buttons)

    def test_navigation_guide_keyboard_adds_workspace_row_for_admin(self) -> None:
        markup = navigation_guide_keyboard("https://era-app.example", admin=True)
        buttons = {button.text: button for row in markup.inline_keyboard for button in row}
        self.assertIn("⚙️ Режим администратора", buttons)
        self.assertEqual(buttons["⚙️ Режим администратора"].web_app.url, "https://era-app.example")

    def test_navigation_guide_keyboard_adds_workspace_row_for_leader(self) -> None:
        markup = navigation_guide_keyboard("https://era-app.example", privileged=True)
        buttons = {button.text: button for row in markup.inline_keyboard for button in row}
        self.assertIn("🧭 Режим лидера", buttons)

    def test_plain_participant_never_sees_the_panel_button(self) -> None:
        # privileged=False, admin=False (the defaults) — a plain
        # participant, in both the miniapp-configured and fallback states.
        without_miniapp = _button_texts(main_inline_keyboard())
        with_miniapp = _button_texts(main_inline_keyboard(miniapp_url="https://era-app.example/"))
        self.assertNotIn("⚙️ Панель", without_miniapp)
        self.assertNotIn("⚙️ Панель", with_miniapp)

    def test_admin_menu_stays_compact_when_miniapp_is_configured(self) -> None:
        # The whole point of the bot/Mini App role split: once the Mini
        # App is configured, an admin's bot-side "main menu" is exactly
        # the same 5 buttons a participant gets — no extra bot-side admin
        # surface, because Admin Mode lives in the Mini App now.
        admin_markup = _button_texts(
            main_inline_keyboard(admin=True, miniapp_url="https://era-app.example/")
        )
        participant_markup = _button_texts(main_inline_keyboard(miniapp_url="https://era-app.example/"))
        self.assertEqual(admin_markup, participant_markup)


if __name__ == "__main__":
    unittest.main()
