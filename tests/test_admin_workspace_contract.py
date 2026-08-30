from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "src"


class AdminWorkspaceContractTests(unittest.TestCase):
    def test_elevated_roles_do_not_replace_personal_miniapp_on_start(self) -> None:
        app = (FRONTEND / "app" / "App.tsx").read_text(encoding="utf-8")
        profile = (FRONTEND / "screens" / "ProfileScreen.tsx").read_text(encoding="utf-8")
        self.assertIn("const [inWorkspace, setInWorkspace] = useState(false)", app)
        self.assertIn('isAdmin ? "Управление ЭРА" : "Пространство лидера"', profile)
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
        self.assertIn("<AdminDashboardScreen />", overview)
        self.assertNotIn("<SystemPanel />", overview)
        self.assertIn("Пульт руководителя", overview)
        self.assertIn("Нужно решить", overview)
        self.assertIn("Быстро сделать", overview)
        self.assertIn("Регистрация и состав", overview)

    def test_admin_navigation_keeps_only_operational_destinations(self) -> None:
        nav = (FRONTEND / "components" / "AdminBottomNav.tsx").read_text(encoding="utf-8")
        for label in ["Обзор", "Люди", "Работа", "Связь"]:
            self.assertIn(f'label: "{label}"', nav)
        for label in ["Контроль", "Аналитика", "Обслуживание"]:
            self.assertNotIn(f'label: "{label}"', nav)


if __name__ == "__main__":
    unittest.main()
