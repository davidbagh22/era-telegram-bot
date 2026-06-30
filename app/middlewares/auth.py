from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.repositories.users import get_user_by_telegram_id


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
            data["user"] = (
                await get_user_by_telegram_id(session, telegram_user.id)
                if telegram_user
                else None
            )
            try:
                result = await handler(event, data)
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise
