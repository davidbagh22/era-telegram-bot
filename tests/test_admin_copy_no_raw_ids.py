"""Admin copy should avoid raw English ID labels in user-facing text."""
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[1]


class AdminCopyNoRawIdsTests(TestCase):
    def test_survey_excel_header_uses_russian_participant_number(self) -> None:
        source = (ROOT / "frontend/src/screens/admin/SurveyResultsDownload.ts").read_text(encoding="utf-8")
        self.assertIn('"Номер участника"', source)
        self.assertNotIn(', "ID"]', source)

    def test_admin_ui_uses_telegram_number_wording(self) -> None:
        for relative in (
            "frontend/src/screens/admin/AdminDataRightsScreen.tsx",
            "frontend/src/screens/admin/AdminApplicationsScreen.tsx",
            "frontend/src/screens/admin/people/PersonDetailRich.tsx",
            "frontend/src/screens/activity/AnniversaryRegistration.tsx",
        ):
            source = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("номер Telegram", source)
            self.assertNotIn("Telegram ID", source)

    def test_contacts_menu_does_not_surface_hash_ids(self) -> None:
        source = (ROOT / "app/handlers/admin/management_ready.py").read_text(encoding="utf-8")
        self.assertIn('text=f"Удалить · {contact.organization_name[:28]}"', source)
        self.assertNotIn('f"#{contact.id} · {contact.organization_name}', source)

    def test_survey_results_fallback_has_no_raw_id_label(self) -> None:
        source = (ROOT / "app/handlers/admin/surveys_analytics.py").read_text(encoding="utf-8")
        self.assertIn('"участник без имени"', source)
        self.assertNotIn('f"ID {response.user_id}"', source)
