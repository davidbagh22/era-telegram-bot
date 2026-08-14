from pathlib import Path
import unittest

from app.services.chat_binding_recovery_service import choose_unique_chat_id


ROOT = Path(__file__).resolve().parents[1]


class ChatBindingRecoveryTests(unittest.TestCase):
    def test_only_one_historical_id_can_be_recovered(self) -> None:
        self.assertEqual(choose_unique_chat_id({-1001234567890}), -1001234567890)
        self.assertIsNone(choose_unique_chat_id(set()))
        self.assertIsNone(choose_unique_chat_id({-1001, -1002}))

    def test_startup_recovery_uses_persisted_evidence_not_invite_links(self) -> None:
        service = (ROOT / "app" / "services" / "chat_binding_recovery_service.py").read_text(encoding="utf-8")
        seed = (ROOT / "app" / "services" / "seed_service.py").read_text(encoding="utf-8")
        for marker in ["ChatGreeting.chat_id", "TaskDelivery.chat_id", "PendingChatJoinRequest.chat_id"]:
            self.assertIn(marker, service)
        self.assertIn("recover_chat_bindings(session, settings)", seed)
        self.assertNotIn("general_chat_url", service)
        self.assertNotIn("internal_department_chat_url", service)
        self.assertNotIn("external_department_chat_url", service)
        self.assertNotIn("leaders_chat_url", service)


if __name__ == "__main__":
    unittest.main()
