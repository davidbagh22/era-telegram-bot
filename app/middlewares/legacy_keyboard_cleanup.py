from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramAPIError
from aiogram.types import ReplyKeyboardRemove, TelegramObject

from app.utils.ux_texts import LEGACY_KEYBOARD_CLEARED
from app.keyboards.bot_shell import main_reply_keyboard
from app.utils.constants import ApplicationStatus, Role

logger = logging.getLogger(__name__)


class LegacyKeyboardCleanupMiddleware(BaseMiddleware):
    """Migrate old clients once, preserving the current persistent menu.

    Approved private profiles receive the current shell, including authorized
    admin shortcuts. Unapproved profiles retain the old cleanup path before
    registration. The legacy flag is reused; no schema or user reset is needed.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("user")
        chat = data.get("event_chat")
        bot = data.get("bot")
        if (
            user is not None
            and not user.legacy_reply_keyboard_removed
            and chat is not None
            and chat.type == "private"
            and bot is not None
        ):
            settings = data.get("settings")
            approved = (
                settings is not None
                and getattr(user, "application_status", None) == ApplicationStatus.APPROVED
                and not getattr(user, "is_blocked", False)
                and not getattr(user, "is_archived", False)
            )
            admin = approved and (
                getattr(user, "role", None) == Role.ADMIN
                or user.telegram_id in getattr(settings, "admin_ids", [])
            )
            # An old migration must never remove the current persistent menu.
            # Pending registrations keep their dedicated input keyboard flow.
            markup = (
                main_reply_keyboard(settings.effective_miniapp_url, admin=bool(admin))
                if approved else ReplyKeyboardRemove()
            )
            notice = (
                "Меню ЭРА обновлено. Статистика доступна по кнопке внизу."
                if admin else "Разделы ЭРА доступны в меню под полем ввода."
                if approved else LEGACY_KEYBOARD_CLEARED
            )
            try:
                await bot.send_message(chat.id, notice, reply_markup=markup)
            except TelegramAPIError as exc:
                # Best-effort — a delivery failure (bot blocked, chat
                # deactivated, transient API error, ...) just means we
                # retry on this user's next Update instead of wrongly
                # marking the one-time migration as done.
                logger.warning(
                    "Could not update private navigation (%s)",
                    type(exc).__name__,
                )
            else:
                user.legacy_reply_keyboard_removed = True
        return await handler(event, data)
