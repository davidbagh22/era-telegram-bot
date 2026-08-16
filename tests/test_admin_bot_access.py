from types import SimpleNamespace

from app.middlewares.admin_bot_access import has_admin_bot_access
from app.utils.constants import Role


def _settings(*admin_ids: int):
    return SimpleNamespace(admin_ids=set(admin_ids))


def _user(role: Role, *, blocked: bool = False, archived: bool = False, grants=()):
    return SimpleNamespace(
        role=role,
        is_blocked=blocked,
        is_archived=archived,
        permission_grants=list(grants),
    )


def test_unrelated_delegated_permission_does_not_unlock_legacy_admin_router() -> None:
    grant = SimpleNamespace(permission="events.manage", is_active=True)
    user = _user(Role.PARTICIPANT, grants=[grant])

    assert has_admin_bot_access(user, _settings(), 1001) is False


def test_admin_role_unlocks_legacy_admin_router() -> None:
    user = _user(Role.ADMIN)

    assert has_admin_bot_access(user, _settings(), 1001) is True


def test_blocked_or_archived_admin_cannot_use_legacy_admin_router() -> None:
    assert has_admin_bot_access(_user(Role.ADMIN, blocked=True), _settings(), 1001) is False
    assert has_admin_bot_access(_user(Role.ADMIN, archived=True), _settings(), 1001) is False


def test_emergency_configured_admin_id_remains_available() -> None:
    assert has_admin_bot_access(None, _settings(1001), 1001) is True
