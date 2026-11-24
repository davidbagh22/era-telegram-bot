import asyncio
from types import SimpleNamespace

from app.middlewares.admin_bot_access import AdminBotAccessFilter, has_admin_bot_access
from app.utils.constants import Role


def _settings(*admin_ids: int):
    return SimpleNamespace(admin_ids=set(admin_ids))


def _user(role: Role, *, telegram_id: int = 1001, blocked: bool = False, archived: bool = False, grants=()):
    return SimpleNamespace(
        telegram_id=telegram_id,
        role=role,
        is_blocked=blocked,
        is_archived=archived,
        permission_grants=list(grants),
    )


def _event(telegram_id: int):
    return SimpleNamespace(from_user=SimpleNamespace(id=telegram_id))


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


def test_configured_admin_id_requires_active_persisted_user() -> None:
    assert has_admin_bot_access(None, _settings(1001), 1001) is False
    assert has_admin_bot_access(_user(Role.PARTICIPANT), _settings(1001), 1001) is True



def test_mismatched_or_missing_persisted_identity_cannot_unlock_admin_router() -> None:
    wrong = _user(Role.ADMIN, telegram_id=2002)
    assert has_admin_bot_access(wrong, _settings(1001), 1001) is False
    assert has_admin_bot_access(wrong, _settings(), 1001) is False
    missing = SimpleNamespace(role=Role.ADMIN, is_blocked=False, is_archived=False)
    assert has_admin_bot_access(missing, _settings(1001), 1001) is False
    assert has_admin_bot_access(_user(Role.ADMIN), _settings(), 1001) is True


def test_delegated_admin_handler_cannot_borrow_another_users_grant() -> None:
    from app.handlers.admin.access import has_admin_bot_access as handler_access

    grant = SimpleNamespace(permission="events.manage", is_active=True)
    matching = _user(Role.PARTICIPANT, grants=[grant])
    wrong = _user(Role.PARTICIPANT, telegram_id=2002, grants=[grant])
    assert handler_access(matching, _settings(), 1001) is True
    assert handler_access(wrong, _settings(1001), 1001) is False
    assert handler_access(wrong, _settings(), 1001) is False
    assert handler_access(_user(Role.PARTICIPANT, blocked=True, grants=[grant]), _settings(), 1001) is False


def test_admin_root_filter_rejects_mismatched_user_and_missing_identity() -> None:
    assert asyncio.run(
        AdminBotAccessFilter()(_event(1001), user=_user(Role.ADMIN, telegram_id=2002), settings=_settings(1001))
    ) is False
    assert asyncio.run(
        AdminBotAccessFilter()(_event(1001), user=None, settings=_settings(1001))
    ) is False

def test_participant_is_skipped_by_admin_root_filter_instead_of_answered_no_access() -> None:
    user = _user(Role.PARTICIPANT)
    result = asyncio.run(
        AdminBotAccessFilter()(_event(1001), user=user, settings=_settings())
    )

    # False is deliberate: Router root-filter semantics mark admin_root as
    # unhandled and allow later participant/leader routers to receive the same
    # callback. The old outer middleware consumed it with a NO_ACCESS alert.
    assert result is False


def test_admin_passes_admin_root_filter() -> None:
    user = _user(Role.ADMIN)
    result = asyncio.run(
        AdminBotAccessFilter()(_event(1001), user=user, settings=_settings())
    )

    assert result is True
