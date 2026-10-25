from pathlib import Path
import unittest

from app.handlers.participant.event_activities_block15 import ALLOWED_PROOF_TYPES


class EventActivitiesBlock15Tests(unittest.TestCase):
    def test_participant_flow_supports_all_proof_types(self) -> None:
        source = Path("app/handlers/participant/event_activities_block15.py").read_text(encoding="utf-8")
        self.assertEqual(
            ALLOWED_PROOF_TYPES,
            {"photo", "link", "text", "file", "video", "manual", "feedback"},
        )
        self.assertIn('F.data.startswith("event:activities:")', source)
        self.assertIn('F.data.startswith("activity:do:")', source)
        self.assertIn('F.data.startswith("activity:submit:")', source)
        self.assertIn('submission.status = "pending"', source)
        self.assertIn("notify_admins", source)
        self.assertIn("safe_send_video", source)

    def test_admin_review_uses_canonical_verified_scoring_gateway(self) -> None:
        source = Path("app/handlers/admin/event_activities_block7.py").read_text(encoding="utf-8")
        self.assertIn("EventActivitySubmission.status.in_(REVIEWABLE_STATUSES)", source)
        self.assertIn('sub.status = "approved"', source)
        self.assertIn('sub.status = "rejected"', source)
        self.assertIn("score_event_activity_completion", source)
        self.assertNotIn("await add_points(", source)
        self.assertIn("sub.points_awarded", source)

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
