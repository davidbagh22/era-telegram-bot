import unittest
from types import SimpleNamespace

from app.utils import ux_texts


class UxEmptyStateTests(unittest.TestCase):
    def test_start_and_main_menu_connect_activity_to_growth(self) -> None:
        combined = ux_texts.WELCOME_START + ux_texts.MAIN_MENU
        self.assertIn("портфолио", combined)
        self.assertIn("рейтинг", combined)
        self.assertIn("возможности", combined)
        self.assertIn("Каждая встреча", combined)

    def test_participant_empty_states_are_alive_and_short(self) -> None:
        states = [
            ux_texts.EVENTS_EMPTY,
            ux_texts.TASKS_EMPTY_ACTIVE,
            ux_texts.TASKS_EMPTY_ARCHIVE,
            ux_texts.REWARDS_EMPTY,
        ]
        for state in states:
            self.assertNotIn("пока нет.", state.lower())
            self.assertLessEqual(len(state), 260)
        self.assertIn("задачи", ux_texts.EVENTS_EMPTY.lower())
        self.assertIn("истории роста", ux_texts.TASKS_EMPTY_ARCHIVE.lower())
        self.assertIn("партнёров", ux_texts.REWARDS_EMPTY.lower())

    def test_rating_empty_state_explains_first_actions(self) -> None:
        body = ux_texts.rating_text([], "—", 0)
        self.assertIn("Рейтинг пока пустой", body)
        self.assertIn("подтверждённых действий", body)
        self.assertIn("ответственность", body)

    def test_profile_completion_hint_points_to_portfolio_documents_and_opportunities(self) -> None:
        user = SimpleNamespace(
            age=None,
            city=None,
            education_work=None,
            email=None,
            phone=None,
        )
        body = ux_texts.profile_empty_hint(user)
        self.assertIn("Профиль ещё можно усилить", body)
        self.assertIn("портфолио", body)
        self.assertIn("документы", body)
        self.assertIn("возможности", body)

    def test_profile_completion_hint_is_empty_when_profile_is_filled(self) -> None:
        user = SimpleNamespace(
            age=21,
            city="Ереван",
            education_work="Университет",
            email="user@example.com",
            phone="+37400000000",
        )
        self.assertEqual(ux_texts.profile_empty_hint(user), "")

    def test_analytics_empty_state_is_ready_for_admin_flow(self) -> None:
        body = ux_texts.analytics_summary(
            users=0,
            approved=0,
            pending=0,
            events=0,
            projects=0,
            contacts=0,
            goals=0,
        )
        self.assertIn("Аналитика пока пустая", body)
        self.assertIn("картина роста ЭРА", body)


if __name__ == "__main__":
    unittest.main()
