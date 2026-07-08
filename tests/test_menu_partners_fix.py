import unittest

from app.keyboards.participant import (
    directions_hub_keyboard,
    portfolio_keyboard,
    profile_sections_keyboard,
    rewards_keyboard,
    tasks_hub_keyboard,
)


class MenuPartnersFixTests(unittest.TestCase):
    def _texts(self, keyboard):
        return [button.text for row in keyboard.inline_keyboard for button in row]

    def _callbacks(self, keyboard):
        return [button.callback_data for row in keyboard.inline_keyboard for button in row if button.callback_data]

    def test_profile_menu_is_compact(self):
        texts = self._texts(profile_sections_keyboard())
        self.assertIn("🎓 Портфолио", texts)
        self.assertIn("🧩 Направления и чаты", texts)
        self.assertIn("✅ Мои задачи", texts)
        self.assertNotIn("⚙️ Настройки профиля", texts)
        self.assertNotIn("🧩 Мои направления", texts)
        self.assertNotIn("➕ Выбрать направление", texts)

    def test_portfolio_has_profile_settings(self):
        callbacks = self._callbacks(portfolio_keyboard())
        self.assertIn("profile:settings", callbacks)

    def test_directions_hub_contains_expected_actions(self):
        callbacks = self._callbacks(directions_hub_keyboard())
        self.assertIn("cabinet:departments", callbacks)
        self.assertIn("department:apply:start", callbacks)

    def test_tasks_hub_contains_sections(self):
        callbacks = self._callbacks(tasks_hub_keyboard())
        self.assertIn("cabinet:tasks:available", callbacks)
        self.assertIn("cabinet:tasks:active", callbacks)
        self.assertIn("cabinet:tasks:archive", callbacks)

    def test_rewards_has_partners_entry(self):
        callbacks = self._callbacks(rewards_keyboard([], []))
        self.assertIn("partners:list", callbacks)


if __name__ == "__main__":
    unittest.main()
