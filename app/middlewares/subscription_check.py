from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.keyboards.common import subscription_keyboard
from app.services.subscription_service import SubscriptionCheckError, is_channel_member
from app.utils import texts
from app.utils.constants import ApplicationStatus


class SubscriptionMiddleware(BaseMiddleware):
    def __init__(self, settings) -> None:
        self.settings = settings

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        message = event.message if isinstance(event, CallbackQuery) else event
        if not isinstance(message, Message) or message.chat.type != "private":
            return await handler(event, data)
        telegram_user = data.get("event_from_user")
        bot = data["bot"]
        try:
            is_member = bool(
                telegram_user and await is_channel_member(bot, telegram_user.id, self.settings)
            )
        except SubscriptionCheckError:
            user = data.get("user")
            if user and user.application_status == ApplicationStatus.APPROVED and not user.is_blocked:
                return await handler(event, data)
            if isinstance(event, CallbackQuery):
                await event.answer()
            await message.answer(
                getattr(
                    texts,
                    "SUBSCRIPTION_CHECK_UNAVAILABLE",
                    "Проверка подписки временно недоступна. Попробуйте позже или напишите администратору.",
                ),
                reply_markup=subscription_keyboard(self.settings.era_channel_url),
            )
            return None
        if is_member:
            return await handler(event, data)
        if isinstance(event, CallbackQuery):
            await event.answer()
        await message.answer(
            texts.SUBSCRIPTION_REQUIRED,
            reply_markup=subscription_keyboard(self.settings.era_channel_url),
        )
        return None
