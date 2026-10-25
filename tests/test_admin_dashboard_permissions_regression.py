from types import SimpleNamespace

from app.services.admin_dashboard_service import has_dashboard_access
from app.utils.constants import Role


def _user(*, role=Role.PARTICIPANT, permissions=(), blocked=False, archived=False, telegram_id=101):
    return SimpleNamespace(
        role=role,
        is_blocked=blocked,
        is_archived=archived,
        telegram_id=telegram_id,
        permission_grants=[
            SimpleNamespace(permission=permission, is_active=True)
            for permission in permissions
        ],
    )


def _settings(*admin_ids):
    return SimpleNamespace(admin_ids=set(admin_ids))


def test_delegated_permission_does_not_unlock_global_command_center() -> None:
    for permission in (
        "people.view",
        "people.manage",
        "events.manage",
        "tasks.manage",
        "partners.manage",
        "analytics.view",
        "portfolio.review",
        "broadcasts.create",
    ):
        user = _user(permissions=(permission,))
        assert has_dashboard_access(user, _settings(), user.telegram_id) is False


def test_database_admin_can_open_global_command_center() -> None:
    user = _user(role=Role.ADMIN)
    assert has_dashboard_access(user, _settings(), user.telegram_id) is True


def test_configured_root_admin_can_open_global_command_center() -> None:
    user = _user(role=Role.PARTICIPANT, telegram_id=202)
    assert has_dashboard_access(user, _settings(202), user.telegram_id) is True


def test_blocked_database_admin_is_denied() -> None:
    user = _user(role=Role.ADMIN, blocked=True)
    assert has_dashboard_access(user, _settings(), user.telegram_id) is False
