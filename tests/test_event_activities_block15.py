from pathlib import Path
import unittest


class EventActivitiesBlock15Tests(unittest.TestCase):
    def test_participant_flow_supports_all_proof_types(self) -> None:
        source = Path("app/handlers/participant/event_activities_block15.py").read_text(encoding="utf-8")
        self.assertIn('{"photo", "link", "text", "file", "manual"}', source)
        self.assertIn('F.data.startswith("event:activities:")', source)
        self.assertIn('F.data.startswith("activity:do:")', source)
        self.assertIn('submission.status = "pending"', source)
        self.assertIn("notify_admins", source)

    def test_admin_review_uses_pending_status_and_points_service(self) -> None:
        source = Path("app/handlers/admin/event_activities_block15.py").read_text(encoding="utf-8")
        self.assertIn('EventActivitySubmission.status == "pending"', source)
        self.assertIn('submission.status = "approved"', source)
        self.assertIn('submission.status = "rejected"', source)
        self.assertIn("await add_points(", source)
        self.assertIn("related_event_id=activity.event_id", source)

    def test_event_card_exposes_activities(self) -> None:
        source = Path("app/handlers/participant/events_stability_block8.py").read_text(encoding="utf-8")
        self.assertIn('text="✨ Активности"', source)
        self.assertIn('callback_data=f"event:activities:{event_id}"', source)
        self.assertIn("EventActivity.is_active.is_(True)", source)

    def test_admin_participant_screen_exposes_activity_management(self) -> None:
        source = Path("app/handlers/admin/event_registration_block14.py").read_text(encoding="utf-8")
        self.assertIn("✨ Управление активностями", source)
        self.assertIn("admin:event:activities:create", source)


if __name__ == "__main__":
    unittest.main()
