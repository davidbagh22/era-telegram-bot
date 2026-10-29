"""Configured ADMIN_IDS must not bypass a persisted user's inactive status.

Isolated authorization checks only: no real roles, users, chats or secrets.
The legacy no-user bootstrap behavior is explicitly preserved pending policy review.
"""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.config import Settings
from app.services.authorization_service import (
    can_manage_events,
    can_manage_partners,
    can_manage_people,
    can_manage_permissions,
    can_manage_tasks,
    can_view_people,
    is_full_admin,
)
from app.services.media_service import can_manage_media
from app.utils.constants import Role


def _user(*, telegram_id=100, blocked=False, archived=False, role=Role.PARTICIPANT):
    return SimpleNamespace(
        telegram_id=telegram_id,
        role=role.value,
        is_blocked=blocked,
        is_archived=archived,
        permission_grants=[],
    )


class ConfiguredAdminInactiveBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings(bot_token="1234567890:LOCALTEST", admin_ids=[100])

    def test_active_configured_admin_retains_existing_permissions(self):
        user = _user()
        self.assertTrue(is_full_admin(user, self.settings, 100))
        for permission in (
            can_view_people,
            can_manage_people,
            can_manage_permissions,
            can_manage_events,
            can_manage_tasks,
            can_manage_partners,
        ):
            with self.subTest(permission=permission.__name__):
                self.assertTrue(permission(user, self.settings, 100))

    def test_blocked_or_archived_configured_admin_is_denied_by_all_helpers(self):
        for user in (_user(blocked=True), _user(archived=True)):
            with self.subTest(blocked=user.is_blocked, archived=user.is_archived):
                self.assertFalse(is_full_admin(user, self.settings, 100))
                for permission in (
                    can_view_people,
                    can_manage_people,
                    can_manage_permissions,
                    can_manage_events,
                    can_manage_tasks,
                    can_manage_partners,
                ):
                    self.assertFalse(permission(user, self.settings, 100))

    def test_mismatched_identity_cannot_inherit_configured_or_role_admin(self):
        for user in (_user(telegram_id=200), _user(telegram_id=200, role=Role.ADMIN)):
            self.assertFalse(is_full_admin(user, self.settings, 100))
            self.assertFalse(can_manage_permissions(user, self.settings, 100))
        self.assertTrue(is_full_admin(_user(role=Role.ADMIN), self.settings, 100))

    def test_mismatched_actor_cannot_use_delegated_global_permissions(self):
        user = _user(telegram_id=200)
        user.permission_grants = [
            SimpleNamespace(
                permission=permission, is_active=True,
                scope_type="global", scope_id=0,
            )
            for permission in (
                "people.view", "people.manage", "events.manage",
                "tasks.manage", "partners.manage",
            )
        ]
        for permission in (
            can_view_people, can_manage_people, can_manage_events,
            can_manage_tasks, can_manage_partners,
        ):
            with self.subTest(permission=permission.__name__):
                self.assertFalse(permission(user, self.settings, 100))
        self.assertTrue(can_manage_events(user, self.settings, 200))

    def test_missing_identity_attribute_is_denied_without_crashing(self):
        user = SimpleNamespace(
            role=Role.ADMIN,
            is_blocked=False,
            is_archived=False,
            permission_grants=[],
        )
        self.assertFalse(is_full_admin(user, self.settings, 100))
        self.assertFalse(can_manage_permissions(user, self.settings, 100))

    def test_legacy_bootstrap_without_persisted_user_is_preserved(self):
        self.assertTrue(is_full_admin(None, self.settings, 100))
        self.assertFalse(is_full_admin(None, self.settings, 200))


class ConfiguredAdminMediaLegacyTests(unittest.IsolatedAsyncioTestCase):
    async def test_inactive_configured_admin_does_not_manage_legacy_media(self):
        settings = Settings(
            bot_token="1234567890:LOCALTEST",
            admin_ids=[100],
            era_chair_user_id=None,
        )
        session = SimpleNamespace(scalar=AsyncMock(return_value=None))
        for user in (_user(blocked=True), _user(archived=True)):
            self.assertFalse(await can_manage_media(session, user, settings))
        self.assertTrue(await can_manage_media(session, _user(), settings))


if __name__ == "__main__":
    unittest.main()
