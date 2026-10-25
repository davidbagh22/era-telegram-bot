from types import SimpleNamespace

from app.services.chat_access_service import check_chat_access
from app.utils.constants import ApplicationStatus, Role


def _media_link(*, status: str, leader_id: int | None = None):
    return SimpleNamespace(
        status=status,
        direction=SimpleNamespace(name="Медиа", leader_id=leader_id),
    )


def _user(*, directions=(), role=Role.PARTICIPANT, user_id=1):
    return SimpleNamespace(
        id=user_id,
        role=role,
        is_blocked=False,
        is_archived=False,
        application_status=ApplicationStatus.APPROVED,
        directions=list(directions),
        departments=[],
    )


def test_plain_approved_participant_cannot_enter_media_chat() -> None:
    decision = check_chat_access(_user(), "media")
    assert decision.allowed is False
    assert decision.reason == "media_approval_required"


def test_pending_media_application_cannot_enter_media_chat() -> None:
    decision = check_chat_access(_user(directions=(_media_link(status="pending"),)), "media")
    assert decision.allowed is False


def test_approved_media_member_can_enter_media_chat() -> None:
    decision = check_chat_access(_user(directions=(_media_link(status="approved"),)), "media")
    assert decision.allowed is True


def test_media_direction_leader_can_enter_media_chat() -> None:
    decision = check_chat_access(
        _user(user_id=7, directions=(_media_link(status="pending", leader_id=7),)),
        "media",
    )
    assert decision.allowed is True


def test_admin_can_enter_media_chat_without_membership() -> None:
    decision = check_chat_access(_user(role=Role.ADMIN), "media")
    assert decision.allowed is True
