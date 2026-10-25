from types import SimpleNamespace

from app.handlers.participant.event_qr import (
    _admin,
    _can_manage_all_qr,
    _can_manage_qr,
    _has_active_permission,
)
from app.utils.constants import Role


def _grant(permission: str, *, active: bool = True):
    return SimpleNamespace(permission=permission, is_active=active)


def _user(role: Role, *grants):
    return SimpleNamespace(role=role, permission_grants=list(grants))


def test_unrelated_permission_never_becomes_admin_or_global_qr_manager() -> None:
    user = _user(Role.PARTICIPANT, _grant("analytics.view"))

    assert _admin(user) is False
    assert _has_active_permission(user, "events.manage") is False
    assert _can_manage_all_qr(user) is False
    assert _can_manage_qr(user) is False


def test_events_manage_explicitly_grants_global_qr_management() -> None:
    user = _user(Role.PARTICIPANT, _grant("events.manage"))

    assert _admin(user) is False
    assert _has_active_permission(user, "events.manage") is True
    assert _can_manage_all_qr(user) is True
    assert _can_manage_qr(user) is True


def test_revoked_events_manage_does_not_grant_qr_management() -> None:
    user = _user(Role.PARTICIPANT, _grant("events.manage", active=False))

    assert _can_manage_all_qr(user) is False
    assert _can_manage_qr(user) is False


def test_leader_can_manage_assigned_qr_but_not_all_events() -> None:
    user = _user(Role.LEADER)

    assert _admin(user) is False
    assert _can_manage_all_qr(user) is False
    assert _can_manage_qr(user) is True


def test_admin_has_global_qr_management_without_grants() -> None:
    user = _user(Role.ADMIN)

    assert _admin(user) is True
    assert _can_manage_all_qr(user) is True
    assert _can_manage_qr(user) is True
