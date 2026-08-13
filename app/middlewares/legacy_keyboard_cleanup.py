from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramAPIError
from aiogram.types import ReplyKeyboardRemove, TelegramObject

from app.utils.ux_texts import LEGACY_KEYBOARD_CLEARED

logger = logging.getLogger(__name__)


class LegacyKeyboardCleanupMiddleware(BaseMiddleware):
    """One-time migration for users whose Telegram client still has the
    bot's old persistent ReplyKeyboardMarkup main menu cached (that
    keyboard builder — main_menu() — has been removed from
    app/keyboards/participant.py; see docs/BOT_VS_MINIAPP_AUDIT.md).
    Telegram keeps a previously-sent persistent reply keyboard visible on
    the client until the bot explicitly sends `ReplyKeyboardRemove()` —
    simply no longer *building* one does not clear what was already sent
    weeks ago, so this can't be skipped even though the keyboard itself is
    gone from the code.

    Registered as an outer Update middleware right after
    DatabaseAuthMiddleware (which populates data["user"]/data["session"]),
    so it runs on the very first Update from a returning user — /start or
    any other message/callback, whichever the user happens to send first —
    not only /start specifically. Gated by
    User.legacy_reply_keyboard_removed so it fires at most once per user,
    ever: no repeat "we updated the app" spam on every later interaction.
    The flag flip lives on the same ORM object DatabaseAuthMiddleware's own
    session.commit() persists at the end of the Update, so no extra commit
    is needed here.

    Private chats only — a group chat has no concept of a per-user
    persistent reply keyboard the way a 1:1 chat does, and firing this per
    group member's first message would just spam the group.
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
            try:
                await bot.send_message(
                    chat.id,
                    LEGACY_KEYBOARD_CLEARED,
                    reply_markup=ReplyKeyboardRemove(),
                )
            except TelegramAPIError:
                # Best-effort — a delivery failure (bot blocked, chat
                # deactivated, transient API error, ...) just means we
                # retry on this user's next Update instead of wrongly
                # marking the one-time migration as done.
                logger.warning(
                    "Failed to send legacy keyboard cleanup notice to telegram_id=%s",
                    user.telegram_id,
                    exc_info=True,
                )
            else:
                user.legacy_reply_keyboard_removed = True
        return await handler(event, data)
