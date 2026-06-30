import unittest

from app.keyboards.participant import main_menu


class BotOnlyTests(unittest.TestCase):
    def test_main_menu_contains_only_telegram_actions(self) -> None:
        keyboard = main_menu(
            "https://t.me/era",
            privileged=True,
            admin=True,
        )
        buttons = [button for row in keyboard.inline_keyboard for button in row]

        self.assertTrue(all(button.web_app is None for button in buttons))
        self.assertIn("cabinet:open", {button.callback_data for button in buttons})
        self.assertIn("admin:panel", {button.callback_data for button in buttons})


if __name__ == "__main__":
    unittest.main()
