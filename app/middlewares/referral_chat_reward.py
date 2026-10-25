from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramAPIError
from aiogram.types import ChatJoinRequest, Message, TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.repositories.users import get_user_by_telegram_id
from app.services.referral_service import award_registration_referral
from app.utils.constants import ApplicationStatus


class ReferralChatRewardMiddleware(BaseMiddleware):
    """Award the referral registration stage only after a real general-chat join.

    It runs *after* the normal chat handler, so it never bypasses join-request
    approval or chat access rules. The points service and referral relationship
    both provide idempotency, therefore Telegram retries/new-member echoes are safe.
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
        bot = data.get("bot")
        if settings is None or session is None or not settings.general_chat_id:
            return result

        if isinstance(event, ChatJoinRequest) and event.chat.id == settings.general_chat_id:
            user = data.get("user")
            if (
                user is not None
                and user.application_status == ApplicationStatus.APPROVED
                and bot is not None
            ):
                try:
                    member = await bot.get_chat_member(event.chat.id, event.from_user.id)
                except TelegramAPIError:
                    member = None
                if member is not None and member.status in {
                    "member",
                    "administrator",
                    "creator",
                    "restricted",
                }:
                    await award_registration_referral(
                        session,
                        invitee_user_id=user.id,
                    )
            return result

        if isinstance(event, Message) and event.chat.id == settings.general_chat_id:
            for member in event.new_chat_members or []:
                if member.is_bot:
                    continue
                joined_user = await get_user_by_telegram_id(session, member.id)
                if (
                    joined_user is not None
                    and joined_user.application_status == ApplicationStatus.APPROVED
                ):
                    await award_registration_referral(
                        session,
                        invitee_user_id=joined_user.id,
                    )
        return result
