from __future__ import annotations

import os
from datetime import datetime, timezone

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.config import Settings
from app.database.models import User
from app.services.authorization_service import can_manage_people
from app.utils import texts

router = Router(name="admin_version_command")
PROCESS_STARTED_AT = datetime.now(timezone.utc)


@router.message(Command("version"))
async def version_command(message: Message, user: User | None, settings: Settings) -> None:
    if not can_manage_people(user, settings, message.from_user.id):
        await message.answer(texts.NO_ACCESS)
        return

    commit = os.environ.get("RENDER_GIT_COMMIT") or os.environ.get("GIT_SHA") or "unknown"
    service = os.environ.get("RENDER_SERVICE_NAME") or "unknown"
    hostname = os.environ.get("RENDER_EXTERNAL_HOSTNAME") or "unknown"
    environment = "render" if os.environ.get("RENDER") or os.environ.get("RENDER_SERVICE_ID") else "local/other"

    await message.answer(
        "🧩 Версия ЭРА Бота\n\n"
        f"Commit: {commit[:12]}\n"
        f"Среда: {environment}\n"
        f"Service: {service}\n"
        f"Host: {hostname}\n"
        f"Процесс запущен: {PROCESS_STARTED_AT:%Y-%m-%d %H:%M:%S} UTC"
    )
