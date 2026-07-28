from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.database.models import User
from app.database.socials import SocialLink, SocialProfile
from app.services.admin_user_card import build_admin_user_card
from app.services.application_review_service import approve_application, reject_application
from app.utils.constants import ApplicationStatus, ParticipationStatus, Role


ROOT = Path(__file__).resolve().parents[1]


class _ScalarResult:
    def __init__(self, items: list[object]) -> None:
        self._items = items

    def all(self) -> list[object]:
        return self._items


def _user(**kwargs) -> User:
    data = {
        "id": 7,
        "telegram_id": 700,
        "username": "era_user",
        "first_name": "Анна",
        "last_name": "Тестова",
        "age": 19,
        "city": "Ереван",
        "email": "anna@example.com",
        "phone": "+374000000",
        "education_work": "Университет",
        "occupation": "Студентка",
        "motivation": "Хочу расти в проектах",
        "available_time": "3-5 часов",
        "desired_path": "Лидер",
        "role": Role.PARTICIPANT,
        "participation_status": ParticipationStatus.NEW_MEMBER,
        "application_status": ApplicationStatus.PENDING,
        "is_blocked": False,
        "is_archived": False,
        "departments": [],
        "directions": [],
        "permission_grants": [],
    }
    data.update(kwargs)
    return User(**data)


def test_application_card_includes_photo_and_socials() -> None:
    session = AsyncMock()
    session.scalar.side_effect = [
        SocialProfile(user_id=7, photo_file_id="photo-file"),
        100,
        2,
    ]
    session.scalars.side_effect = [
        _ScalarResult([SocialLink(user_id=7, platform="Instagram", url="https://instagram.com/era")]),
        _ScalarResult([]),
    ]

    card = asyncio.run(build_admin_user_card(session, _user(), mode="application"))

    assert card.photo_file_id == "photo-file"
    assert "Заявка #7" in card.text
    assert "Анна Тестова" in card.text
    assert "Instagram: https://instagram.com/era" in card.text
    assert "Мотивация" in card.text
    assert "admin:approve_user:7" in str(card.reply_markup)
    assert "admin:reject_user:7" in str(card.reply_markup)


def test_admin_user_card_marks_missing_photo_and_socials() -> None:
    session = AsyncMock()
    session.scalar.side_effect = [None, 0, 0]
    session.scalars.side_effect = [_ScalarResult([]), _ScalarResult([])]

    card = asyncio.run(build_admin_user_card(session, _user(), mode="profile"))

    assert card.photo_file_id is None
    assert "Фото: не загружено" in card.text
    assert "Соцсети\nне указаны" in card.text
    assert "admin:user:points:7" in str(card.reply_markup)


def test_admin_user_routes_use_single_presenter() -> None:
    registration = (ROOT / "app/handlers/registration.py").read_text(encoding="utf-8")
    panel = (ROOT / "app/handlers/admin/panel.py").read_text(encoding="utf-8")
    profile = (ROOT / "app/handlers/admin/user_profile_block3_safe.py").read_text(encoding="utf-8")
    rights = (ROOT / "app/handlers/admin/rights_block6.py").read_text(encoding="utf-8")

    assert "send_admin_application_cards" in registration
    assert "_application_notification" not in registration
    assert "send_admin_user_card(call.message, session, target, mode=\"application\")" in panel
    assert "send_admin_user_card(call.message, session, target, mode=\"profile\")" in profile
    assert "send_admin_user_card(call.message, session, target, mode=\"profile\")" in rights


def test_approve_application_is_idempotent_and_blocks_rejected() -> None:
    session = AsyncMock()
    target = _user(application_status=ApplicationStatus.PENDING)

    with patch("app.services.application_review_service.add_points", new=AsyncMock()) as points, patch(
        "app.services.application_review_service.audit", new=AsyncMock()
    ) as audit:
        first = asyncio.run(approve_application(session, target, actor_id=1))
        second = asyncio.run(approve_application(session, target, actor_id=1))

    assert first.changed is True
    assert first.code == "approved"
    assert target.application_status == ApplicationStatus.APPROVED
    assert target.role == Role.PARTICIPANT
    assert second.changed is False
    assert second.code == "already_approved"
    points.assert_awaited_once()
    audit.assert_awaited_once()

    rejected = _user(application_status=ApplicationStatus.REJECTED)
    result = asyncio.run(approve_application(session, rejected, actor_id=1))
    assert result.changed is False
    assert result.code == "already_rejected"


def test_reject_application_is_idempotent_and_blocks_approved() -> None:
    session = AsyncMock()
    target = _user(application_status=ApplicationStatus.PENDING)

    with patch("app.services.application_review_service.audit", new=AsyncMock()) as audit:
        first = asyncio.run(reject_application(session, target, actor_id=1, comment="Не сейчас"))
        second = asyncio.run(reject_application(session, target, actor_id=1, comment="Не сейчас"))

    assert first.changed is True
    assert first.code == "rejected"
    assert target.application_status == ApplicationStatus.REJECTED
    assert second.changed is False
    assert second.code == "already_rejected"
    audit.assert_awaited_once()

    approved = _user(application_status=ApplicationStatus.APPROVED)
    result = asyncio.run(reject_application(session, approved, actor_id=1, comment="Не сейчас"))
    assert result.changed is False
    assert result.code == "already_approved"
