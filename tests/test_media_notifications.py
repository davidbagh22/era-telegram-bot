from __future__ import annotations

import asyncio
from pathlib import Path

from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendDocument, SendPhoto, SendVideo

from app.services.notification_service import safe_send_document, safe_send_photo, safe_send_video


ROOT = Path(__file__).resolve().parents[1]


class FakeMediaBot:
    def __init__(self, *, fail: str | None = None) -> None:
        self.fail = fail
        self.calls: list[tuple[str, int, str]] = []

    async def send_photo(self, chat_id: int, photo, caption=None, reply_markup=None) -> None:
        self.calls.append(("photo", chat_id, photo))
        if self.fail == "photo":
            raise TelegramForbiddenError(method=SendPhoto(chat_id=chat_id, photo=photo), message="blocked")

    async def send_document(self, chat_id: int, document, caption=None, reply_markup=None) -> None:
        self.calls.append(("document", chat_id, str(document)))
        if self.fail == "document":
            raise TelegramForbiddenError(method=SendDocument(chat_id=chat_id, document=document), message="blocked")

    async def send_video(self, chat_id: int, video, caption=None, reply_markup=None) -> None:
        self.calls.append(("video", chat_id, video))
        if self.fail == "video":
            raise TelegramForbiddenError(method=SendVideo(chat_id=chat_id, video=video), message="blocked")


def test_safe_media_helpers_return_delivery_status() -> None:
    bot = FakeMediaBot()

    assert asyncio.run(safe_send_photo(bot, 1, "photo-id")) is True
    assert asyncio.run(safe_send_document(bot, 1, "doc-id")) is True
    assert asyncio.run(safe_send_video(bot, 1, "video-id")) is True
    assert bot.calls == [
        ("photo", 1, "photo-id"),
        ("document", 1, "doc-id"),
        ("video", 1, "video-id"),
    ]


def test_safe_media_helpers_swallow_telegram_delivery_errors() -> None:
    assert asyncio.run(safe_send_photo(FakeMediaBot(fail="photo"), 1, "photo-id")) is False
    assert asyncio.run(safe_send_document(FakeMediaBot(fail="document"), 1, "doc-id")) is False
    assert asyncio.run(safe_send_video(FakeMediaBot(fail="video"), 1, "video-id")) is False


def test_submission_media_notifications_use_safe_helpers() -> None:
    task_source = (ROOT / "app/handlers/participant/task_block2.py").read_text(encoding="utf-8")
    activity_source = (ROOT / "app/handlers/participant/event_activities_block15.py").read_text(encoding="utf-8")
    project_source = (ROOT / "app/handlers/participant/projects_block5.py").read_text(encoding="utf-8")
    event_card_source = (ROOT / "app/services/event_card.py").read_text(encoding="utf-8")

    assert "safe_send_photo" in task_source
    assert "safe_send_video" in task_source
    assert "safe_send_document" in task_source
    assert "await bot.send_photo(chat_id, file_id" not in task_source
    assert "await bot.send_video(chat_id, file_id" not in task_source
    assert "await bot.send_document(chat_id, file_id" not in task_source

    assert "safe_send_photo" in activity_source
    assert "safe_send_document" in activity_source
    assert "await bot.send_photo(chat_id, submission.file_id" not in activity_source
    assert "await bot.send_document(chat_id, submission.file_id" not in activity_source

    assert "safe_send_document" in project_source
    assert "await bot.send_document(chat_id, BufferedInputFile" not in project_source

    assert "safe_send_photo" in event_card_source
    assert "safe_send(bot, chat_id, text" in event_card_source
