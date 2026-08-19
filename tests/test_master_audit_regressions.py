from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.config import Settings
from app.services.activity_scoring_service import scoped_task_points
from app.services.admin_dashboard_service import has_dashboard_access
from app.services.chat_access_service import check_chat_access
from app.utils.constants import ApplicationStatus, ParticipationStatus, Role


def _settings() -> Settings:
    return Settings(bot_token="1234567890:test-token")


def _permission(name: str) -> SimpleNamespace:
    return SimpleNamespace(permission=name, is_active=True)


def _user(**overrides) -> SimpleNamespace:
    defaults = dict(
        id=1,
        telegram_id=777,
        role=Role.PARTICIPANT,
        participation_status=ParticipationStatus.NEW_MEMBER,
        application_status=ApplicationStatus.APPROVED,
        is_blocked=False,
        is_archived=False,
        permission_grants=[],
        directions=[],
        departments=[],
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class AdminPermissionBoundaryTests(unittest.TestCase):
    def test_narrow_permission_never_grants_global_command_center(self) -> None:
        user = _user(permission_grants=[_permission("analytics.view")])
        self.assertFalse(has_dashboard_access(user, _settings(), user.telegram_id))

    def test_admin_role_can_open_global_command_center(self) -> None:
        user = _user(role=Role.ADMIN)
        self.assertTrue(has_dashboard_access(user, _settings(), user.telegram_id))


class ScopedMultiplierTests(unittest.TestCase):
    def test_project_curator_gets_105_only_on_role_scoped_task(self) -> None:
        participant = _user(participation_status=ParticipationStatus.PROJECT_CURATOR)
        scoped = SimpleNamespace(points=100, reward_json={"role_scoped": True}, project_id=None)
        ordinary = SimpleNamespace(points=100, reward_json={}, project_id=None)

        self.assertEqual(scoped_task_points(scoped, participant), 105)
        self.assertEqual(scoped_task_points(ordinary, participant), 100)

    def test_leader_multiplier_is_not_stacked_with_curator_rank(self) -> None:
        participant = _user(
            role=Role.LEADER,
            participation_status=ParticipationStatus.PROJECT_CURATOR,
        )
        task = SimpleNamespace(points=100, reward_json={"role_scoped": True}, project_id=None)
        self.assertEqual(scoped_task_points(task, participant), 110)


class MediaChatPermissionTests(unittest.TestCase):
    def test_approved_participant_without_media_membership_is_denied(self) -> None:
        decision = check_chat_access(_user(), "media")
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "media_approval_required")

    def test_approved_media_member_is_allowed(self) -> None:
        direction = SimpleNamespace(name="Медиа", leader_id=None)
        link = SimpleNamespace(direction=direction, status="approved")
        decision = check_chat_access(_user(directions=[link]), "media")
        self.assertTrue(decision.allowed)


if __name__ == "__main__":
    unittest.main()
