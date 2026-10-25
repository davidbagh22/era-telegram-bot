import unittest

from app.utils import ux_texts


class UxEmptyStateTests(unittest.TestCase):
    def test_required_ux_empty_states_are_present(self) -> None:
        values = [
            ux_texts.WELCOME_START,
            ux_texts.MAIN_MENU,
            ux_texts.EVENTS_EMPTY,
            ux_texts.TASKS_EMPTY_ACTIVE,
            ux_texts.TASKS_EMPTY_ARCHIVE,
            ux_texts.REWARDS_EMPTY,
            ux_texts.CONTACT_MENU,
            ux_texts.ANALYTICS_EMPTY,
        ]
        for value in values:
            self.assertIsInstance(value, str)
            self.assertTrue(value.strip())

    def test_growth_meaning_is_kept_in_core_copy(self) -> None:
        combined = "\n".join([ux_texts.WELCOME_START, ux_texts.MAIN_MENU])
        self.assertIn("портфолио", combined)
        self.assertIn("рейтинг", combined)
        self.assertIn("возможности", combined)


if __name__ == "__main__":
    unittest.main()
