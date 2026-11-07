"""Issue #541: blocked or archived configured admins must never pass legacy guards."""
from types import SimpleNamespace
from unittest import TestCase

from app.utils.constants import Role
from app.handlers.admin import (
    addons, approval_bonus_fix, chat_binding_stability,
    event_activities_block7, event_activities_stability,
    management_ready, partners_admin, user_profile_block3_safe, panel,
)


def _user(**changes):
    row = dict(role=Role.ADMIN, is_blocked=False, is_archived=False,
               permission_grants=[])
    row.update(changes)
    return SimpleNamespace(**row)


class LegacyAdminBlockTests(TestCase):
    def test_all_direct_admin_guards_fail_closed_for_blocked_or_archived(self):
        settings = SimpleNamespace(admin_ids=[7])
        probes = (
            ("addons", lambda u: addons._is_admin(u, settings, 7)),
            ("approval", lambda u: approval_bonus_fix._admin_ok(u, settings, 7)),
            ("chat", lambda u: chat_binding_stability._can_bind(u, settings, 7)),
            ("activities7", lambda u: event_activities_block7.is_admin(u, settings, 7)),
            ("activities", lambda u: event_activities_stability._is_admin(u, settings, 7)),
            ("management", lambda u: management_ready._is_admin(u, settings, 7)),
            ("partners", lambda u: partners_admin._is_admin(u, settings, 7)),
            ("profile", lambda u: user_profile_block3_safe.is_admin(u, settings, 7, None)),
            ("panel", lambda u: panel._is_admin(u, settings, 7, None)),
        )
        for name, check in probes:
            with self.subTest(name=name, variant="active"):
                self.assertTrue(check(_user()))
            for flag in ("is_blocked", "is_archived"):
                with self.subTest(name=name, variant=flag):
                    self.assertFalse(check(_user(**{flag: True})))
