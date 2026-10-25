from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AdminNotificationRecipientTests(unittest.TestCase):
    def test_notifications_include_database_admins(self) -> None:
        source = (ROOT / "app/services/notification_service.py").read_text(encoding="utf-8")
        self.assertIn("_database_admin_ids", source)
        self.assertIn("admin_notification_recipients", source)
        self.assertIn("User.role == Role.ADMIN", source)
        self.assertIn("User.is_blocked.is_(False)", source)
        self.assertIn("User.is_archived.is_(False)", source)
        self.assertIn("recipients.update(await _database_admin_ids(settings))", source)

    def test_automatic_admin_notifications_do_not_include_leaders_chat(self) -> None:
        notification_source = (ROOT / "app/services/notification_service.py").read_text(encoding="utf-8")
        broadcast_source = (ROOT / "app/services/admin_broadcast_service.py").read_text(encoding="utf-8")

        # New registration cards and their fallback both resolve recipients
        # through admin_notification_recipients(). The leaders group must never
        # be injected into that automatic recipient set.
        self.assertNotIn("recipients.add(settings.leaders_chat_id)", notification_source)

        # This fix must not remove the owner's explicit Admin Mode ability to
        # send a task/reminder/broadcast to the leaders chat on purpose.
        self.assertIn('"leaders": settings.leaders_chat_id', broadcast_source)

    def test_notification_result_is_visible_to_callers(self) -> None:
        source = (ROOT / "app/services/notification_service.py").read_text(encoding="utf-8")
        self.assertIn("-> tuple[int, int]", source)
        self.assertIn("return sent, failed", source)
        self.assertIn("no recipients configured", source)

    def test_broadcast_has_deduplication_rate_limit_and_retry_contracts(self) -> None:
        source = (ROOT / "app/services/notification_service.py").read_text(encoding="utf-8")
        self.assertIn("broadcast_detailed", source)
        self.assertIn("_dedupe_recipients", source)
        self.assertIn("asyncio.Semaphore", source)
        self.assertIn("TelegramRetryAfter", source)
        self.assertIn("TelegramForbiddenError", source)


if __name__ == "__main__":
    unittest.main()
