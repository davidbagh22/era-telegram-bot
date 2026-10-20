from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiogram.types import InlineKeyboardMarkup

from app.services.admin_user_card import send_admin_application_cards

ROOT = Path(__file__).resolve().parents[1]

def _card():
    return SimpleNamespace(text="application-card", photo_file_id=None, reply_markup=InlineKeyboardMarkup(inline_keyboard=[]))

def _settings():
    return SimpleNamespace(effective_miniapp_url="")

def test_total_application_delivery_failure_triggers_registration_fallback() -> None:
    with patch("app.services.admin_user_card.build_admin_user_card", new=AsyncMock(return_value=_card())), patch("app.services.admin_user_card.notify_admins_once", new=AsyncMock(return_value=(0, 2, 0))):
        try:
            asyncio.run(send_admin_application_cards(object(), _settings(), AsyncMock(), SimpleNamespace(id=7)))
        except RuntimeError as exc:
            assert str(exc) == "application_card_delivery_failed"
        else:
            raise AssertionError("Total notification failure must not be silent")

def test_successful_application_delivery_remains_non_failing() -> None:
    with patch("app.services.admin_user_card.build_admin_user_card", new=AsyncMock(return_value=_card())), patch("app.services.admin_user_card.notify_admins_once", new=AsyncMock(return_value=(1, 0, 0))):
        result = asyncio.run(send_admin_application_cards(object(), _settings(), AsyncMock(), SimpleNamespace(id=7)))
    assert result == (1, 0)


def test_photo_is_forwarded_with_caption_within_telegram_limit() -> None:
    card = _card()
    card.photo_file_id = 'uploaded-photo'
    card.text = 'Анкета ' * 700
    with patch('app.services.admin_user_card.build_admin_user_card', AsyncMock(return_value=card)), patch(
        'app.services.admin_user_card.notify_admins_once', AsyncMock(return_value=(1, 0, 0)),
    ) as notify:
        asyncio.run(send_admin_application_cards(object(), _settings(), AsyncMock(), SimpleNamespace(id=7)))
    assert notify.await_args.kwargs['photo'] == 'uploaded-photo'
    assert len(notify.await_args.args[2]) <= 1024
    assert notify.await_args.kwargs['parse_mode'] == ''

def test_admin_bot_has_database_backed_application_recovery() -> None:
    source = (ROOT / "app/handlers/admin/dashboard_block_a.py").read_text(encoding="utf-8")
    assert '@applications_router.message(Command("applications"))' in source
    from app.handlers.admin import project_review_router
    from app.handlers.admin.dashboard_block_a import applications_router
    assert applications_router.parent_router is project_review_router
    assert "ApplicationStatus.PENDING" in source
    assert "ApplicationStatus.NEEDS_INFO" in source
    assert "User.is_archived.is_not(True)" in source
    assert 'mode="application"' in source
