"""Configured ADMIN_IDS must not receive private admin cards after revocation.

Pure mocked database tests: no production DB, Telegram messages or role changes.
"""
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from app.services.notification_service import admin_notification_recipients


class _Session:
    def __init__(self, rows):
        self.rows = rows

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, statement):
        assert "users" in str(statement)
        return SimpleNamespace(all=lambda: self.rows)


class ConfiguredAdminRecipientTests(IsolatedAsyncioTestCase):
    async def test_revoked_configured_ids_are_removed_but_absent_bootstrap_is_preserved(self):
        settings = SimpleNamespace(admin_ids=[11, 22, 33, 44], database_url="unused")
        # 44 is intentionally absent from users; the configured bootstrap remains.
        rows = [(11, False, False), (22, True, False), (33, False, True)]
        with patch("app.services.notification_service._session_factory", return_value=lambda: _Session(rows)), \\
             patch("app.services.notification_service._database_admin_ids", new=AsyncMock(return_value={55})):
            recipients = await admin_notification_recipients(settings)
        self.assertEqual(recipients, {11, 44, 55})

    async def test_unverified_configured_ids_fail_closed_on_database_error(self):
        settings = SimpleNamespace(admin_ids=[11, 22], database_url="unused")
        with patch("app.services.notification_service._session_factory", side_effect=RuntimeError("offline")), \\
             patch("app.services.notification_service._database_admin_ids", new=AsyncMock(return_value=set())):
            recipients = await admin_notification_recipients(settings)
        self.assertEqual(recipients, set())

    async def test_database_admins_work_when_no_bootstrap_ids_configured(self):
        settings = SimpleNamespace(admin_ids=[], database_url="unused")
        with patch("app.services.notification_service._session_factory") as factory, \\
             patch("app.services.notification_service._database_admin_ids", new=AsyncMock(return_value={55})):
            recipients = await admin_notification_recipients(settings)
        self.assertEqual(recipients, {55})
        factory.assert_not_called()
