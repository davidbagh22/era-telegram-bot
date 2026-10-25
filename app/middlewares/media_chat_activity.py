from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.services.media_chat_activity_service import is_human_content_message, record_media_chat_message


class MediaChatActivityMiddleware(BaseMiddleware):
    """DELTA ToR §38-41: counts human messages in the linked Media chat for
    the "activity in Media Chat" metric, without ever touching message
    content or routing. Same "outer middleware observes, never consumes"
    shape as ReferralChatRewardMiddleware -- runs after the real handler,
    so it can never block or shadow existing Media chat file/reply flows.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        result = await handler(event, data)
        settings: Settings | None = data.get("settings")
        session: AsyncSession | None = data.get("session")
        if (
            settings is not None
            and session is not None
            and settings.media_chat_id is not None
            and isinstance(event, Message)
            and event.chat.id == settings.media_chat_id
            and is_human_content_message(event)
        ):
            await record_media_chat_message(
                session, chat_id=event.chat.id, telegram_user_id=event.from_user.id
            )
        return result
