from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "src"


class AdminWorkspaceContractTests(unittest.TestCase):
    def test_elevated_roles_do_not_replace_personal_miniapp_on_start(self) -> None:
        app = (FRONTEND / "app" / "App.tsx").read_text(encoding="utf-8")
        profile = (FRONTEND / "screens" / "ProfileScreen.tsx").read_text(encoding="utf-8")
        self.assertIn("const [inWorkspace, setInWorkspace] = useState(false)", app)
        self.assertIn("Управление ЭРА", profile)
        self.assertIn("onEnterWorkspace", profile)
        self.assertIn("onEnterWorkspace", app)
        self.assertIn("adminWorkspaceRequested", app)

    def test_control_is_a_dedicated_admin_destination(self) -> None:
        nav = (FRONTEND / "components" / "AdminBottomNav.tsx").read_text(encoding="utf-8")
        screen = (FRONTEND / "screens" / "AdminScreen.tsx").read_text(encoding="utf-8")
        self.assertIn('label: "Контроль"', nav)
        for marker in ['value: "analytics"', 'value: "system"', 'value: "maintenance"', "<AdminDashboardScreen", "<SystemPanel />", "<AdminMaintenanceScreen />"]:
            self.assertIn(marker, screen)

    def test_overview_and_communications_do_not_duplicate_control_tools(self) -> None:
        overview = (FRONTEND / "screens" / "admin" / "AdminOverviewScreen.tsx").read_text(encoding="utf-8")
        tools = (FRONTEND / "screens" / "admin" / "AdminToolsScreen.tsx").read_text(encoding="utf-8")
        self.assertNotIn("AdminDashboardScreen", overview)
        self.assertNotIn("AdminMaintenanceScreen", overview)
        self.assertNotIn("SystemPanel", tools)
        self.assertNotIn('value: "system"', tools)


if __name__ == "__main__":
    unittest.main()
