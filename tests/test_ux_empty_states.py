import unittest

from app.utils import ux_texts


_AI_TEMPLATE_FRAGMENTS = (
    "Участвуйте. Создавайте. Собирайте команду.",
    "формируют ваш путь",
    "история роста",
    "Это не пауза",
    "Хороший момент",
    "след Вашей активности",
    "войти в движение",
    "картина роста",
    "не гонка за цифрой",
    "быстро оживает",
)


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

    def test_ux_copy_avoids_ai_template_fragments(self) -> None:
        values = [
            ux_texts.WELCOME_START,
            ux_texts.MAIN_MENU,
            ux_texts.MAIN_INLINE_MENU,
            ux_texts.CABINET_EMPTY_HINT,
            ux_texts.EVENTS_EMPTY,
            ux_texts.TASKS_EMPTY_ACTIVE,
            ux_texts.TASKS_EMPTY_ARCHIVE,
            ux_texts.OPPORTUNITIES_MENU.format(balance=0),
            ux_texts.REWARDS_MENU.format(balance=0),
            ux_texts.REWARDS_EMPTY,
            ux_texts.CONTACT_MENU,
            ux_texts.TEAM_MENU,
            ux_texts.ANALYTICS_EMPTY,
            ux_texts.journey_intro("Анна", False),
            ux_texts.rating_text([], 1, 0),
        ]
        combined = "\n".join(values)
        offenders = [fragment for fragment in _AI_TEMPLATE_FRAGMENTS if fragment in combined]
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
