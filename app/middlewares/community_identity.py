from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import ChatJoinRequest, Message, TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import User
from app.services.community_verification_service import observe_member_identity


class CommunityIdentityMiddleware(BaseMiddleware):
    """Remember known Telegram identities without creating User duplicates.

    Telegram does not expose a reliable full member-list API to bots, so the
    verification roster is built from identities the managed general chat has
    actually observed: messages, service join/leave updates and join requests.
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
        user: User | None = data.get("user")
        if settings is None or session is None or not settings.general_chat_id:
            return result

        if isinstance(event, ChatJoinRequest) and event.chat.id == settings.general_chat_id:
            await observe_member_identity(
                session,
                telegram_id=event.from_user.id,
                general_chat_id=event.chat.id,
                user=user,
                is_current_member=False,
                seen_at=event.date,
            )
            return result

        if not isinstance(event, Message) or event.chat.id != settings.general_chat_id:
            return result

        if event.from_user and not event.from_user.is_bot:
            await observe_member_identity(
                session,
                telegram_id=event.from_user.id,
                general_chat_id=event.chat.id,
                user=user,
                is_current_member=True,
                seen_at=event.date,
            )
        for member in event.new_chat_members or []:
            if member.is_bot:
                continue
            linked_user = user if user and user.telegram_id == member.id else None
            await observe_member_identity(
                session,
                telegram_id=member.id,
                general_chat_id=event.chat.id,
                user=linked_user,
                is_current_member=True,
                seen_at=event.date,
            )
        if event.left_chat_member and not event.left_chat_member.is_bot:
            linked_user = user if user and user.telegram_id == event.left_chat_member.id else None
            await observe_member_identity(
                session,
                telegram_id=event.left_chat_member.id,
                general_chat_id=event.chat.id,
                user=linked_user,
                is_current_member=False,
                seen_at=event.date,
            )
        return result
