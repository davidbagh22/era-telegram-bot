from __future__ import annotations

from aiogram.types import CallbackQuery, Message

from app.config import Settings
from app.database.models import User
from app.services.authorization_service import is_full_admin
from app.utils import texts


def has_admin_bot_access(user: User | None, settings: Settings, telegram_id: int) -> bool:
    if is_full_admin(user, settings, telegram_id):
        return True
    if not user or user.is_blocked or user.is_archived:
        return False
    return any(grant.is_active for grant in (user.permission_grants or []))


async def guard_admin_bot(
    event: Message | CallbackQuery,
    user: User | None,
    settings: Settings,
) -> bool:
    telegram_id = event.from_user.id
    target = event.message if isinstance(event, CallbackQuery) else event
    if not has_admin_bot_access(user, settings, telegram_id):
        if isinstance(event, CallbackQuery):
            await event.answer()
        if target is not None:
            await target.answer(texts.NO_ACCESS)
        return False
    return True
