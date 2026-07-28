from __future__ import annotations

import asyncio
from pathlib import Path

from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.methods import SendMessage

from app.services.notification_service import broadcast, broadcast_detailed


ROOT = Path(__file__).resolve().parents[1]


def _method(chat_id: int = 1) -> SendMessage:
    return SendMessage(chat_id=chat_id, text="test")


class FakeBot:
    def __init__(self, failures: dict[int, list[Exception]] | None = None, delay: float = 0.0) -> None:
        self.failures = failures or {}
        self.delay = delay
        self.calls: list[int] = []
        self.active = 0
        self.max_active = 0

    async def send_message(self, chat_id: int, text: str, reply_markup=None) -> None:
        self.calls.append(chat_id)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            planned = self.failures.get(chat_id) or []
            if planned:
                raise planned.pop(0)
        finally:
            self.active -= 1


def test_broadcast_deduplicates_recipients() -> None:
    bot = FakeBot()

    result = asyncio.run(broadcast_detailed(bot, [1, 2, 1, "2", 3], "Привет"))

    assert result.total == 3
    assert result.duplicates == 2
    assert result.sent == 3
    assert result.failed == 0
    assert bot.calls == [1, 2, 3]


def test_broadcast_retries_retry_after_once() -> None:
    bot = FakeBot(
        {
            1: [
                TelegramRetryAfter(method=_method(1), message="Too Many Requests", retry_after=0),
            ]
        }
    )

    result = asyncio.run(broadcast_detailed(bot, [1], "Привет", max_attempts=2))

    assert result.sent == 1
    assert result.failed == 0
    assert bot.calls == [1, 1]


def test_broadcast_does_not_retry_permanent_forbidden_error() -> None:
    bot = FakeBot({1: [TelegramForbiddenError(method=_method(1), message="bot was blocked")]})

    result = asyncio.run(broadcast_detailed(bot, [1], "Привет", max_attempts=3))

    assert result.sent == 0
    assert result.failed == 1
    assert result.permanent_failed == 1
    assert result.temporary_failed == 0
    assert bot.calls == [1]


def test_broadcast_limits_concurrency() -> None:
    bot = FakeBot(delay=0.01)

    result = asyncio.run(broadcast_detailed(bot, range(10), "Привет", concurrency=2))

    assert result.sent == 10
    assert bot.max_active <= 2


def test_legacy_broadcast_returns_sent_failed_tuple() -> None:
    bot = FakeBot({2: [TelegramForbiddenError(method=_method(2), message="bot was blocked")]})

    sent, failed = asyncio.run(broadcast(bot, [1, 2, 1], "Привет"))

    assert (sent, failed) == (1, 1)


def test_admin_mass_broadcast_uses_detailed_result() -> None:
    source = (ROOT / "app/handlers/admin/panel.py").read_text(encoding="utf-8")

    assert "broadcast_detailed" in source
    assert "result.duplicates" in source
    assert "result.temporary_failed" in source
    assert "result.permanent_failed" in source


def test_survey_broadcast_uses_detailed_delivery_result() -> None:
    source = (ROOT / "app/handlers/admin/surveys_analytics.py").read_text(encoding="utf-8")

    assert "from app.services.notification_service import broadcast_detailed" in source
    assert "result = await broadcast_detailed(" in source
    assert "participant.telegram_id for participant in recipients" in source
    assert "reply_markup=keyboard" in source
    assert "result.duplicates" in source
    assert "result.temporary_failed" in source
    assert "result.permanent_failed" in source
    assert "for participant in recipients:\n        ok = await safe_send" not in source


def test_chat_broadcast_uses_safe_send_contract() -> None:
    source = (ROOT / "app/handlers/admin/management_ready.py").read_text(encoding="utf-8")

    assert "from app.services.notification_service import safe_send" in source
    assert "ok = await safe_send(bot, chat_id, text)" in source
    assert "await bot.send_message(chat_id, text)" not in source
    assert "TelegramAPIError" not in source
