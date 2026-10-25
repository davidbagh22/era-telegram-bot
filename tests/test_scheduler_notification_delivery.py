from __future__ import annotations

from pathlib import Path

from app.services.notification_service import BroadcastFailure, BroadcastResult
from app.services.scheduler_service import _delivery_finished


ROOT = Path(__file__).resolve().parents[1]


def test_delivery_finished_keeps_temporary_failures_retryable() -> None:
    result = BroadcastResult(
        total=1,
        failed=1,
        failures=[BroadcastFailure(chat_id=1, reason="TelegramNetworkError", temporary=True)],
    )

    assert _delivery_finished(result) is False


def test_delivery_finished_advances_success_or_permanent_failure() -> None:
    assert _delivery_finished(BroadcastResult(total=1, sent=1)) is True
    assert (
        _delivery_finished(
            BroadcastResult(
                total=1,
                failed=1,
                failures=[BroadcastFailure(chat_id=1, reason="TelegramForbiddenError", temporary=False)],
            )
        )
        is True
    )


def test_scheduler_reminders_keep_retry_and_recipient_contracts() -> None:
    source = (ROOT / "app/services/scheduler_service.py").read_text(encoding="utf-8")

    # Legacy/admin broadcasts still use the detailed delivery contract so
    # temporary Telegram failures do not advance reminder state.
    assert "from app.services.notification_service import (" in source
    assert "broadcast_detailed" in source
    assert "admin_notification_recipients" in source
    assert "if not _delivery_finished(result):\n            logger.warning(" in source
    assert "if not _delivery_finished(result):\n                continue" in source

    # Participant event/task reminders use the single-primary-action shell.
    # Event stages do not advance after a failed delivery; task stages advance
    # only when every eligible recipient completed delivery.
    assert "send_bot_notification" in source
    assert "if not sent:\n                    continue" in source
    assert "if expected_recipients and completed_recipients < expected_recipients:\n                continue" in source

    # Automatic admin recipients are resolved centrally, never from a stale
    # environment-only ADMIN_IDS snapshot inside the scheduler.
    assert "settings.admin_ids" not in source
