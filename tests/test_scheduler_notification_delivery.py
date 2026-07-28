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


def test_scheduler_reminders_use_detailed_delivery_contracts() -> None:
    source = (ROOT / "app/services/scheduler_service.py").read_text(encoding="utf-8")

    assert "from app.services.notification_service import (" in source
    assert "broadcast_detailed" in source
    assert "admin_notification_recipients" in source
    assert "if not _delivery_finished(result):\n                    continue" in source
    assert "if not _delivery_finished(result):\n            logger.warning(" in source
    assert "if not _delivery_finished(result):\n                continue" in source
    assert "or (not telegram_ids and creator is None)" in source
    assert "settings.admin_ids" not in source
