from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "src"


class AdminWorkspaceContractTests(unittest.TestCase):
    def test_elevated_roles_do_not_replace_personal_miniapp_on_start(self) -> None:
        app = (FRONTEND / "app" / "App.tsx").read_text(encoding="utf-8")
        profile = (FRONTEND / "screens" / "ProfileScreen.tsx").read_text(encoding="utf-8")
        self.assertIn("const [inWorkspace, setInWorkspace] = useState(false)", app)
        self.assertIn('isAdmin ? "Управление ЭРА" : "Режим лидера"', profile)
        self.assertIn("onEnterWorkspace", app)

    def test_admin_overview_is_the_single_simple_control_surface(self) -> None:
        nav = (FRONTEND / "components" / "AdminBottomNav.tsx").read_text(encoding="utf-8")
        screen = (FRONTEND / "screens" / "AdminScreen.tsx").read_text(encoding="utf-8")
        overview = (FRONTEND / "screens" / "admin" / "AdminOverviewScreen.tsx").read_text(encoding="utf-8")

        self.assertNotIn('label: "Контроль"', nav)
        self.assertNotIn('"control"', nav)
        self.assertNotIn("ControlSection", screen)
        self.assertNotIn("AdminMaintenanceScreen", screen)
        self.assertNotIn("CONTROL_SECTIONS", screen)
        self.assertIn("<AdminDashboardScreen onAction=", overview)
        self.assertNotIn("<SystemPanel />", overview)
        self.assertIn("Пульт руководителя", overview)
        self.assertIn("Решить сегодня", overview)
        self.assertIn("Быстро сделать", overview)
        self.assertIn("Регистрация и состав", overview)

    def test_decide_today_queues_open_concrete_resolvers(self) -> None:
        """Решить сегодня must not dump admins on a section menu."""
        overview = (FRONTEND / "screens" / "admin" / "AdminOverviewScreen.tsx").read_text(encoding="utf-8")
        screen = (FRONTEND / "screens" / "AdminScreen.tsx").read_text(encoding="utf-8")
        events = (FRONTEND / "screens" / "admin" / "AdminEventsScreen.tsx").read_text(encoding="utf-8")
        projects = (FRONTEND / "screens" / "admin" / "AdminProjectsScreen.tsx").read_text(encoding="utf-8")

        self.assertIn("projects_review: onOpenProjectReview", overview)
        self.assertIn("events_pending: onOpenEventModeration", overview)
        self.assertIn("activity_results: onOpenActivityResults", overview)
        self.assertIn('projects: { section: "moderation" }', screen)
        self.assertIn('events: { section: "moderation" }', screen)
        self.assertIn('events: { section: "activities", activitiesMode: "review" }', screen)
        self.assertIn("initialSection", events)
        self.assertIn("initialActivitiesMode", events)
        self.assertIn("initialSection", projects)

    def test_appoint_leader_keeps_selected_user_for_expected_role(self) -> None:
        appoint = (FRONTEND / "screens" / "admin" / "AdminAppointLeaderScreen.tsx").read_text(
            encoding="utf-8"
        )
        self.assertIn("setSelectedUser", appoint)
        self.assertIn("expected_role: selectedUser.role", appoint)
        self.assertNotIn("candidates.find((item) => item.id === userId)", appoint)
        self.assertIn("Выбран:", appoint)

    def test_admin_navigation_keeps_only_operational_destinations(self) -> None:
        nav = (FRONTEND / "components" / "AdminBottomNav.tsx").read_text(encoding="utf-8")
        for label in ["Обзор", "Люди", "Работа", "Связь"]:
            self.assertIn(f'label: "{label}"', nav)
        for label in ["Контроль", "Аналитика", "Обслуживание"]:
            self.assertNotIn(f'label: "{label}"', nav)

    def test_leader_overview_uses_task_status_labels(self) -> None:
        overview = (FRONTEND / "screens" / "leader" / "OverviewTab.tsx").read_text(encoding="utf-8")
        self.assertIn('published: "Открыт набор"', overview)
        self.assertIn('review: "На проверке"', overview)
        self.assertNotIn("submitted:", overview)
        self.assertNotIn("approved:", overview)


if __name__ == "__main__":
    unittest.main()
