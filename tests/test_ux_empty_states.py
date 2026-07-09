import unittest

from app.utils import ux_texts


class UxEmptyStateTests(unittest.TestCase):
    def test_ux_copy_module_exposes_required_empty_states(self) -> None:
        required = [
            ux_texts.WELCOME_START,
            ux_texts.MAIN_MENU,
            ux_texts.EVENTS_EMPTY,
            ux_texts.TASKS_EMPTY_ACTIVE,
            ux_texts.TASKS_EMPTY_ARCHIVE,
            ux_texts.REWARDS_EMPTY,
            ux_texts.CONTACT_MENU,
            ux_texts.ANALYTICS_EMPTY,
        ]
        for value in required:
            self.assertIsInstance(value, str)
            self.assertTrue(value.strip())

    def test_ux_copy_keeps_growth_meaning(self) -> None:
        combined = "\n".join(
            [
                ux_texts.WELCOME_START,
                ux_texts.MAIN_MENU,
                ux_texts.OPPORTUNITIES_MENU,
            ]
        )
        self.assertIn("портфолио", combined)
        self.assertIn("рейтинг", combined)
        self.assertIn("возможности", combined)

    def test_dynamic_empty_state_helpers_return_text(self) -> None:
        rating = ux_texts.rating_text([], "—", 0)
        analytics = ux_texts.analytics_summary(
            users=0,
            approved=0,
            pending=0,
            events=0,
            projects=0,
            contacts=0,
            goals=0,
        )
        self.assertTrue(rating.strip())
        self.assertTrue(analytics.strip())
        self.assertIn("Рейтинг", rating)
        self.assertIn("Аналитика", analytics)


if __name__ == "__main__":
    unittest.main()
