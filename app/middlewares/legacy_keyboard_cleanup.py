from __future__ import annotations

import hashlib
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramAPIError
from aiogram.types import ReplyKeyboardRemove, TelegramObject

from sqlalchemy import select, text

from app.database.models import AppSetting
from app.utils.ux_texts import LEGACY_KEYBOARD_CLEARED
from app.keyboards.bot_shell import has_leaders_entry, main_reply_keyboard
from app.services import anniversary_registration_service as anniversary
from app.services.media_leadership_service import is_media_chair
from app.utils.constants import ApplicationStatus, Role

logger = logging.getLogger(__name__)

# Bump when reply-shell layout or labels change so clients refresh once.
PRIVATE_MENU_VERSION = "2026-11-18-admin-hub-ticket"


class LegacyKeyboardCleanupMiddleware(BaseMiddleware):
    """Migrate old clients once, preserving the current persistent menu.

    Approved private profiles receive the current shell, including authorized
    admin shortcuts. Unapproved profiles retain the old cleanup path before
    registration. A versioned setting refreshes already-migrated clients once. No user reset or schema change is needed.
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
            session = data.get("session")
            menu_key = f"private-menu:{user.telegram_id}"
            leaders = approved and has_leaders_entry(user)
            media = approved and bool(settings) and is_media_chair(user, settings)
            featured = False
            anniversary_registered = False
            if approved and session is not None:
                featured = await anniversary.menu_available(session)
                if featured:
                    anniversary_registered = await anniversary.user_already_registered(
                        session, user.telegram_id, user,
                    )
            # Replace previously cached simple-mode WebApp reply buttons on
            # the user's next private update, without a proactive broadcast.
            version = {
                "version": PRIVATE_MENU_VERSION,
                "admin": bool(admin),
                "leaders": bool(leaders),
                "media": bool(media),
                "anniversary": bool(featured),
                "anniversary_ticket": bool(anniversary_registered),
            }
            saved_menu = None
            if approved and session is not None:
                if session.bind.dialect.name == "postgresql":
                    lock_id = int.from_bytes(hashlib.blake2b(menu_key.encode(), digest_size=8).digest(), "big", signed=True)
                    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_id})
                saved_menu = await session.scalar(select(AppSetting).where(AppSetting.key == menu_key))
                if saved_menu is not None and saved_menu.value == version:
                    return await handler(event, data)
            elif user.legacy_reply_keyboard_removed:
                return await handler(event, data)
            # An old migration must never remove the current persistent menu.
            # Pending registrations keep their dedicated input keyboard flow.
            markup = (
                main_reply_keyboard(
                    settings.effective_miniapp_url,
                    admin=bool(admin),
                    leaders=bool(leaders),
                    media_chair=bool(media),
                    anniversary=bool(featured),
                    anniversary_registered=bool(anniversary_registered),
                )
                if approved else ReplyKeyboardRemove()
            )
            notice = (
                "Меню ЭРА обновлено. Админ-раздел — кнопка ⚙️ Админ рядом со «Связь»."
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
                if approved and session is not None:
                    if saved_menu is None:
                        session.add(AppSetting(key=menu_key, value=version))
                    else:
                        saved_menu.value = version
                    await session.flush()
        return await handler(event, data)
