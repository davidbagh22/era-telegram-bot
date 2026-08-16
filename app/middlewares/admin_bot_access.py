from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.config import Settings
from app.database.models import User
from app.utils import texts
from app.utils.constants import Role


def has_admin_bot_access(
    user: User | None,
    settings: Settings,
    telegram_id: int,
) -> bool:
    """Keep bot-native admin routes admin-only.

    Delegated permissions are enforced by the Mini App/API per capability.
    They must not make a user admin-equivalent for the legacy Telegram admin
    router, where older handlers share broad guards.
    """
    return bool(
        telegram_id in settings.admin_ids
        or (
            user
            and user.role == Role.ADMIN
            and not user.is_blocked
            and not user.is_archived
        )
    )


class AdminBotAccessMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("user")
        settings = data.get("settings")
        telegram_user = data.get("event_from_user")

        if (
            settings is not None
            and telegram_user is not None
            and has_admin_bot_access(user, settings, telegram_user.id)
        ):
            return await handler(event, data)

        if isinstance(event, CallbackQuery):
            await event.answer(texts.NO_ACCESS, show_alert=True)
        elif isinstance(event, Message):
            await event.answer(texts.NO_ACCESS)
        return None
