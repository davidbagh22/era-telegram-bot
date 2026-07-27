from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from app.config import Settings
from app.services.authorization_service import (
    active_permissions,
    can_change_access_status,
    can_change_permission,
    can_change_role,
    can_manage_people,
    can_view_people,
)
from app.utils.constants import Role


def _user(
    *,
    user_id: int = 1,
    telegram_id: int = 100,
    role: Role | str = Role.PARTICIPANT,
    blocked: bool = False,
    archived: bool = False,
    permissions: tuple[str, ...] = (),
):
    return SimpleNamespace(
        id=user_id,
        telegram_id=telegram_id,
        role=role.value if isinstance(role, Role) else role,
        is_blocked=blocked,
        is_archived=archived,
        permission_grants=[
            SimpleNamespace(permission=permission, is_active=True)
            for permission in permissions
        ],
    )


class AuthorizationServiceAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_user_cannot_change_own_role_even_by_direct_callback(self) -> None:
        session = SimpleNamespace(scalar=AsyncMock(return_value=2))
        settings = Settings(bot_token="1234567890:test", admin_ids=[])
        actor = _user(user_id=1, role=Role.ADMIN)

        decision = await can_change_role(
            session,
            actor=actor,
            actor_telegram_id=actor.telegram_id,
            target=actor,
            new_role=Role.PARTICIPANT,
            settings=settings,
        )

        self.assertFalse(decision.allowed)
        self.assertIn("собственную роль", decision.reason)

    async def test_last_admin_cannot_be_demoted_blocked_or_archived(self) -> None:
        session = SimpleNamespace(scalar=AsyncMock(return_value=1))
        settings = Settings(bot_token="1234567890:test", admin_ids=[])
        actor = _user(user_id=1, role=Role.ADMIN)
        target = _user(user_id=2, telegram_id=200, role=Role.ADMIN)

        role_decision = await can_change_role(
            session,
            actor=actor,
            actor_telegram_id=actor.telegram_id,
            target=target,
            new_role=Role.LEADER,
            settings=settings,
        )
        access_decision = await can_change_access_status(
            session, actor=actor, target=target, settings=settings
        )

        self.assertFalse(role_decision.allowed)
        self.assertIn("последнего администратора", role_decision.reason)
        self.assertFalse(access_decision.allowed)
        self.assertIn("последнего администратора", access_decision.reason)

    async def test_primary_settings_admin_cannot_be_demoted_or_disabled(self) -> None:
        session = SimpleNamespace(scalar=AsyncMock(return_value=2))
        settings = Settings(bot_token="1234567890:test", admin_ids=[200])
        actor = _user(user_id=1, role=Role.ADMIN)
        target = _user(user_id=2, telegram_id=200, role=Role.ADMIN)

        role_decision = await can_change_role(
            session,
            actor=actor,
            actor_telegram_id=actor.telegram_id,
            target=target,
            new_role=Role.LEADER,
            settings=settings,
        )
        access_decision = await can_change_access_status(
            session, actor=actor, target=target, settings=settings
        )

        self.assertFalse(role_decision.allowed)
        self.assertIn("Основного администратора", role_decision.reason)
        self.assertFalse(access_decision.allowed)
        self.assertIn("Основного администратора", access_decision.reason)

    async def test_user_cannot_toggle_own_permissions(self) -> None:
        user = _user(user_id=1, role=Role.ADMIN)

        decision = await can_change_permission(actor=user, target=user)

        self.assertFalse(decision.allowed)
        self.assertIn("собственные права", decision.reason)


def test_delegated_people_permissions_do_not_grant_full_admin() -> None:
    settings = Settings(bot_token="1234567890:test", admin_ids=[])
    viewer = _user(permissions=("people.view",))
    manager = _user(permissions=("people.manage",))

    assert can_view_people(viewer, settings, viewer.telegram_id)
    assert not can_manage_people(viewer, settings, viewer.telegram_id)
    assert can_manage_people(manager, settings, manager.telegram_id)


def test_blocked_user_loses_delegated_permissions_immediately() -> None:
    settings = Settings(bot_token="1234567890:test", admin_ids=[])
    blocked = _user(blocked=True, permissions=("people.manage",))

    assert active_permissions(blocked) == {"people.manage"}
    assert not can_view_people(blocked, settings, blocked.telegram_id)
    assert not can_manage_people(blocked, settings, blocked.telegram_id)
