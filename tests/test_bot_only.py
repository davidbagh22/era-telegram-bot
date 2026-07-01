import unittest

from app.keyboards.admin import admin_panel_keyboard
from app.keyboards.participant import main_menu
from app.keyboards.registration import pending_registration_keyboard
from app.states.registration import RegistrationStates
from app.utils import texts
from app.utils.constants import (
    EVENT_STATUS_LABELS,
    PROJECT_STATUS_LABELS,
    REGISTRATION_STATUS_LABELS,
    TASK_STATUS_LABELS,
    EventStatus,
    ProjectStatus,
    RegistrationStatus,
    TaskStatus,
)


class BotOnlyTests(unittest.TestCase):
    def test_main_menu_contains_only_telegram_actions(self) -> None:
        keyboard = main_menu(
            "https://t.me/era",
            privileged=True,
            admin=True,
        )
        buttons = [button for row in keyboard.keyboard for button in row]

        self.assertTrue(all(button.web_app is None for button in buttons))
        labels = {button.text for button in buttons}
        self.assertIn("🌱 Мой путь", labels)
        self.assertIn("⚙️ Управление", labels)
        self.assertTrue(keyboard.is_persistent)

    def test_pending_registration_has_a_clear_next_step(self) -> None:
        keyboard = pending_registration_keyboard("https://t.me/era")
        callbacks = {
            button.callback_data
            for row in keyboard.inline_keyboard
            for button in row
            if button.callback_data
        }

        self.assertIn("registration:status", callbacks)

    def test_removed_skills_question_is_not_in_registration_flow(self) -> None:
        self.assertFalse(hasattr(RegistrationStates, "skills"))
        self.assertFalse(hasattr(RegistrationStates, "experience"))
        self.assertFalse(hasattr(texts, "REG_SKILLS"))

    def test_admin_panel_is_compact(self) -> None:
        keyboard = admin_panel_keyboard()

        self.assertEqual(len(keyboard.inline_keyboard), 3)
        self.assertTrue(all(len(row) == 2 for row in keyboard.inline_keyboard))

    def test_every_public_status_has_a_human_label(self) -> None:
        self.assertEqual(set(EVENT_STATUS_LABELS), set(EventStatus))
        self.assertEqual(set(PROJECT_STATUS_LABELS), set(ProjectStatus))
        self.assertEqual(set(REGISTRATION_STATUS_LABELS), set(RegistrationStatus))
        self.assertEqual(set(TASK_STATUS_LABELS), set(TaskStatus))


if __name__ == "__main__":
    unittest.main()
