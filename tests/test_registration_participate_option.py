import unittest

from app.keyboards.registration import directions_keyboard


class RegistrationParticipateOptionTests(unittest.TestCase):
    def test_participate_option_is_available_for_every_department_scope(self) -> None:
        for scope in ("internal", "external", "both", "unsure"):
            markup = directions_keyboard(scope)
            callbacks = {
                button.callback_data
                for row in markup.inline_keyboard
                for button in row
                if button.callback_data
            }
            self.assertIn("reg:dir:participate", callbacks, msg=f"Нет кнопки для scope={scope}")


if __name__ == "__main__":
    unittest.main()
