import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.repositories.users import get_user_by_telegram_id
from app.services.digital_engagement_service import award_daily_open

logger = logging.getLogger(__name__)


class DatabaseAuthMiddleware(BaseMiddleware):
    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with self.session_factory() as session:
            data["session"] = session
            telegram_user = data.get("event_from_user")
            user = (
                await get_user_by_telegram_id(session, telegram_user.id)
                if telegram_user
                else None
            )
            data["user"] = user
            if user is not None:
                # Digital-engagement daily-open bonus (ToR section 5). Best
                # effort: a bug here must never break the actual handler, so
                # it's isolated and logged rather than left to bubble up.
                try:
                    await award_daily_open(session, user)
                except Exception:
                    logger.exception("digital engagement award_daily_open failed for user %s", user.id)
            try:
                result = await handler(event, data)
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise
