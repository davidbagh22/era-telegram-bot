from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from time import monotonic
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.config import Settings
from app.services.chat_permissions_service import restore_general_chat_member

logger = logging.getLogger(__name__)


class LegacyChatPermissionRecoveryMiddleware(BaseMiddleware):
    """Repair historical per-user mutes when a person contacts ERA Bot.

    Telegram keeps a `restrictChatMember` override until it is explicitly
    replaced, even after the bot stops applying registration-based mutes. The
    Bot API cannot list every historical group member, so unknown/unregistered
    people cannot be repaired by the periodic database sweep alone.

    This outer Update middleware handles that gap: the first private interaction
    from any Telegram account gives us its id, and we immediately inspect that
    exact account in the general chat and restore write permissions if Telegram
    still reports it as `restricted`.

    A small in-process cooldown prevents repeated getChatMember calls while a
    person is actively using the bot. It is intentionally not persisted: after
    a process restart we prefer one harmless re-check over leaving someone muted.
    """

    def __init__(self, settings: Settings, *, cooldown_seconds: int = 600) -> None:
        self.settings = settings
        self.cooldown_seconds = cooldown_seconds
        self._checked_at: dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        chat = data.get("event_chat")
        from_user = data.get("event_from_user")
        bot = data.get("bot")

        if (
            chat is not None
            and getattr(chat, "type", None) == "private"
            and from_user is not None
            and bot is not None
            and getattr(from_user, "id", None)
        ):
            telegram_id = int(from_user.id)
            now = monotonic()
            previous = self._checked_at.get(telegram_id)
            if previous is None or now - previous >= self.cooldown_seconds:
                self._checked_at[telegram_id] = now
                try:
                    await restore_general_chat_member(bot, self.settings, telegram_id)
                except Exception:
                    # Permission repair is best-effort infrastructure work. A
                    # transient Telegram failure must never block the user's
                    # actual /start, registration or Mini App flow.
                    logger.warning(
                        "Legacy chat permission recovery failed telegram_id=%s",
                        telegram_id,
                        exc_info=True,
                    )

        return await handler(event, data)
