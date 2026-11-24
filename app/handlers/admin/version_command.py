from __future__ import annotations

import os
from datetime import datetime, timezone

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import User
from app.services.authorization_service import can_manage_people
from app.utils import texts

router = Router(name="admin_version_command")
PROCESS_STARTED_AT = datetime.now(timezone.utc)


@router.message(Command("version"))
async def version_command(
    message: Message,
    user: User | None,
    settings: Settings,
    bot: Bot,
    session: AsyncSession,
) -> None:
    if not can_manage_people(user, settings, message.from_user.id):
        await message.answer(texts.NO_ACCESS)
        return

    commit = os.environ.get("RENDER_GIT_COMMIT") or os.environ.get("GIT_SHA") or "unknown"
    service = os.environ.get("RENDER_SERVICE_NAME") or "unknown"
    hostname = os.environ.get("RENDER_EXTERNAL_HOSTNAME") or "unknown"
    environment = "render" if os.environ.get("RENDER") or os.environ.get("RENDER_SERVICE_ID") else "local/other"

    # Live checks against Telegram and the DB, not just static env vars —
    # this is what actually answers "does this exact process serve the
    # bot you're talking to right now", not just "the deploy succeeded".
    # No secrets in any of these values: bot username/id are public
    # (anyone can find them via Telegram search), a webhook host is not a
    # secret (the actual secret is the header token, sent separately, not
    # part of this URL).
    try:
        me = await bot.get_me()
        bot_identity = f"@{me.username} (номер {me.id})"
    except Exception:
        bot_identity = "ошибка запроса к Telegram"

    try:
        menu_button = await bot.get_chat_menu_button()
        menu_types = {"web_app": "мини-приложение", "commands": "команды", "default": "по умолчанию"}
        menu_button_line = menu_types.get(menu_button.type, menu_button.type)
        if menu_button.type == "web_app":
            menu_button_line += f" → {menu_button.web_app.url}"
    except Exception:
        menu_button_line = "ошибка запроса к Telegram"

    try:
        webhook_info = await bot.get_webhook_info()
        webhook_line = (
            f"{webhook_info.url or 'не настроен'} "
            f"(в очереди: {webhook_info.pending_update_count}"
            + (f", последняя ошибка: {webhook_info.last_error_message}" if webhook_info.last_error_message else "")
            + ")"
        )
    except Exception:
        webhook_line = "ошибка запроса к Telegram"

    try:
        await session.execute(sql_text("SELECT 1"))
        db_line = "доступна"
    except Exception:
        db_line = "НЕДОСТУПНА"

    environment_label = "Render" if environment == "render" else "локальная / другая"
    if commit == "unknown":
        commit = "нет данных"
    if service == "unknown":
        service = "не указан"
    if hostname == "unknown":
        hostname = "не указан"

    await message.answer(
        "🧩 Версия и диагностика ЭРА\n\n"
        f"Сборка: {commit[:12]}\n"
        f"Среда: {environment_label}\n"
        f"Сервис: {service}\n"
        f"Хост: {hostname}\n"
        f"Процесс запущен: {PROCESS_STARTED_AT:%Y-%m-%d %H:%M:%S} UTC\n\n"
        f"Бот: {bot_identity}\n"
        f"Кнопка меню: {menu_button_line}\n"
        f"Мини-приложение: {settings.effective_miniapp_url or 'не настроено'}\n"
        f"Приём обновлений: {webhook_line}\n"
        f"База данных: {db_line}"
    )
