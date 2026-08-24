from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiogram.types import InlineKeyboardMarkup

from app.services.admin_user_card import send_admin_application_cards


ROOT = Path(__file__).resolve().parents[1]


def _card():
    return SimpleNamespace(
        text="application-card",
        photo_file_id=None,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[]),
    )


def _settings():
    return SimpleNamespace(effective_miniapp_url="")


def test_total_application_delivery_failure_triggers_registration_fallback() -> None:
    with patch(
        "app.services.admin_user_card.build_admin_user_card",
        new=AsyncMock(return_value=_card()),
    ), patch(
        "app.services.admin_user_card.admin_notification_recipients",
        new=AsyncMock(return_value=[1001, 1002]),
    ), patch(
        "app.services.admin_user_card.safe_send",
        new=AsyncMock(return_value=False),
    ):
        try:
            asyncio.run(
                send_admin_application_cards(
                    object(),
                    _settings(),
                    AsyncMock(),
                    SimpleNamespace(id=7),
                )
            )
        except RuntimeError as exc:
            assert str(exc) == "application_card_delivery_failed"
        else:
            raise AssertionError("Total notification failure must not be silent")


def test_successful_application_delivery_remains_non_failing() -> None:
    with patch(
        "app.services.admin_user_card.build_admin_user_card",
        new=AsyncMock(return_value=_card()),
    ), patch(
        "app.services.admin_user_card.admin_notification_recipients",
        new=AsyncMock(return_value=[1001]),
    ), patch(
        "app.services.admin_user_card.safe_send",
        new=AsyncMock(return_value=True),
    ):
        result = asyncio.run(
            send_admin_application_cards(
                object(),
                _settings(),
                AsyncMock(),
                SimpleNamespace(id=7),
            )
        )

    assert result == (1, 0)


def test_admin_bot_has_database_backed_application_recovery() -> None:
    source = (ROOT / "app/handlers/admin/dashboard_block_a.py").read_text(
        encoding="utf-8"
    )

    assert '@router.message(Command("applications"))' in source
    assert "ApplicationStatus.PENDING" in source
    assert "ApplicationStatus.NEEDS_INFO" in source
    assert "User.is_archived.is_not(True)" in source
    assert 'mode="application"' in source
