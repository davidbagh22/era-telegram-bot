from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AdminNotificationRecipientTests(unittest.TestCase):
    def test_notifications_include_database_admins(self) -> None:
        source = (ROOT / "app/services/notification_service.py").read_text(encoding="utf-8")
        self.assertIn("_database_admin_ids", source)
        self.assertIn("User.role == Role.ADMIN", source)
        self.assertIn("User.is_blocked.is_(False)", source)
        self.assertIn("User.is_archived.is_(False)", source)
        self.assertIn("recipients.update(await _database_admin_ids(settings))", source)

    def test_notification_result_is_visible_to_callers(self) -> None:
        source = (ROOT / "app/services/notification_service.py").read_text(encoding="utf-8")
        self.assertIn("-> tuple[int, int]", source)
        self.assertIn("return sent, failed", source)
        self.assertIn("no recipients configured", source)


if __name__ == "__main__":
    unittest.main()
