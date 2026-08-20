from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.database.models import Department, User, UserDepartment
from app.services.chat_access_service import (
    access_message,
    chat_key_for_id,
    check_chat_access,
    restricted_permissions,
    writable_permissions,
)
from app.utils.constants import ApplicationStatus, Role


ROOT = Path(__file__).resolve().parents[1]


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        general_chat_id=-1001,
        internal_department_chat_id=-1002,
        external_department_chat_id=-1003,
        leaders_chat_id=-1004,
        chat_ids={-1001, -1002, -1003, -1004},
    )


def _user(**kwargs) -> User:
    data = {
        "telegram_id": 10,
        "first_name": "Тест",
        "role": Role.PARTICIPANT,
        "application_status": ApplicationStatus.APPROVED,
        "is_blocked": False,
        "is_archived": False,
        "departments": [],
        "directions": [],
    }
    data.update(kwargs)
    return User(**data)


def _with_department(name: str) -> User:
    department = Department(name=name)
    user = _user()
    user.departments = [UserDepartment(department=department)]
    return user


def test_chat_key_for_bound_chat_ids() -> None:
    settings = _settings()

    assert chat_key_for_id(settings, -1001) == "general"
    assert chat_key_for_id(settings, -1002) == "internal"
    assert chat_key_for_id(settings, -1003) == "external"
    assert chat_key_for_id(settings, -1004) == "leaders"
    assert chat_key_for_id(settings, -9999) is None


def test_access_requires_registration_and_approval() -> None:
    missing = check_chat_access(None, "general")
    pending = check_chat_access(_user(application_status=ApplicationStatus.PENDING), "general")
    rejected = check_chat_access(_user(application_status=ApplicationStatus.REJECTED), "general")

    assert missing.allowed is False
    assert missing.pending is True
    assert missing.reason == "not_registered"
    assert pending.allowed is False
    assert pending.pending is True
    assert pending.reason == "not_approved"
    assert rejected.allowed is False
    assert rejected.pending is False
    assert rejected.reason == "rejected"


def test_access_depends_on_chat_type_and_role() -> None:
    approved = _user()

    assert check_chat_access(approved, "general").allowed is True
    assert check_chat_access(_with_department("Внутренние связи"), "internal").allowed is True
    assert check_chat_access(_with_department("Внешние связи"), "external").allowed is True
    assert check_chat_access(_with_department("Внешние связи"), "internal").reason == "wrong_department"
    assert check_chat_access(_user(role=Role.LEADER), "leaders").allowed is True
    assert check_chat_access(_user(role=Role.PARTICIPANT), "leaders").reason == "wrong_role"
    assert check_chat_access(_user(role=Role.ADMIN), "leaders").allowed is True


def test_blocked_and_archived_users_are_denied() -> None:
    assert check_chat_access(_user(is_blocked=True), "general").reason == "blocked"
    assert check_chat_access(_user(is_archived=True), "general").reason == "archived"


def test_permissions_match_telegram_restriction_model() -> None:
    restricted = restricted_permissions()
    writable = writable_permissions()

    assert restricted.can_send_messages is False
    assert restricted.can_send_photos is False
    assert restricted.can_send_other_messages is False
    assert writable.can_send_messages is True
    assert writable.can_send_photos is True
    assert writable.can_send_other_messages is True


def test_user_facing_access_messages_are_specific() -> None:
    assert "регистрацию" in access_message("not_registered").casefold()
    assert "дождитесь" in access_message("not_approved").casefold()
    assert "лидерам" in access_message("wrong_role").casefold()


def test_chat_handlers_keep_join_access_without_write_restrictions() -> None:
    chat_source = (ROOT / "app/handlers/chat.py").read_text(encoding="utf-8")
    service_source = (ROOT / "app/services/chat_access_service.py").read_text(encoding="utf-8")
    # The live user-approval path is approval_bonus_fix.py::approve_user_with_100_points
    # — panel.py had its own admin:approve_user: handler once, but it was
    # already permanently shadowed by approval_bonus_fix.py's identical
    # callback_data pattern (registered earlier in
    # app/handlers/admin/__init__.py) and was removed as confirmed-dead
    # code in PR 33; this assertion no longer applies to panel.py.
    approval_source = (ROOT / "app/handlers/admin/approval_bonus_fix.py").read_text(encoding="utf-8")
    rights_source = (ROOT / "app/handlers/admin/rights_block6.py").read_text(encoding="utf-8")

    assert "@router.chat_join_request()" in chat_source
    assert "handle_chat_join_request" in chat_source
    assert "restrict_member(bot, message.chat.id" not in chat_source
    assert "await remove_rejected_member(bot" not in service_source
    assert "else await restrict_member" not in service_source
    assert "await unrestrict_member(bot, chat_id, user.telegram_id)" in service_source
    assert "Право писать остаётся у всех." in chat_source
    assert "ban_chat_member" not in chat_source
    assert "approve_chat_join_request" in service_source
    assert "decline_chat_join_request" in service_source
    assert "restrict_chat_member" in service_source
    assert "PendingChatJoinRequest" in service_source
    assert "sync_user_chat_access(bot, settings, session, target)" in approval_source
    assert "sync_user_chat_access(bot, settings, session, target)" in rights_source
