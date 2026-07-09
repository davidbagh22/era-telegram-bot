from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import AppSetting, ChatGreeting, User
from app.utils.constants import Role

router = Router(name="chat_binding")

CHAT_KEYS = {
    "general": ("general_chat_id", "general", "Общий чат"),
    "internal": ("internal_department_chat_id", "internal", "Внутренние связи"),
    "external": ("external_department_chat_id", "external", "Внешние связи"),
    "leaders": ("leaders_chat_id", "leaders", "Чат лидеров"),
    "channel": ("era_channel_id", "era_channel", "Канал ЭРА"),
    "era_channel": ("era_channel_id", "era_channel", "Канал ЭРА"),
}


def _can_bind(user: User | None, settings: Settings, telegram_id: int) -> bool:
    return bool(
        telegram_id in settings.admin_ids
        or (user and user.role == Role.ADMIN and not user.is_blocked and not user.is_archived)
    )


@router.message(Command("bind"), ~F.chat.type.in_({"private"}))
async def bind_current_chat(message: Message, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not message.from_user or not _can_bind(user, settings, message.from_user.id):
        await message.reply("Привязать чат может только администратор ЭРА")
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or parts[1].strip().lower() not in CHAT_KEYS:
        await message.reply(
            "Напишите так: /bind general\n\n"
            "Варианты: general, internal, external, leaders, channel"
        )
        return
    raw_key = parts[1].strip().lower()
    setting_key, greeting_key, title = CHAT_KEYS[raw_key]
    stored = await session.scalar(select(AppSetting).where(AppSetting.key == setting_key))
    if stored is None:
        stored = AppSetting(key=setting_key, value=str(message.chat.id), updated_by=user.id if user else None)
        session.add(stored)
    else:
        stored.value = str(message.chat.id)
        stored.updated_by = user.id if user else None
    greeting = await session.scalar(select(ChatGreeting).where(ChatGreeting.chat_key == greeting_key))
    if greeting is not None:
        greeting.chat_id = message.chat.id
        greeting.updated_by = user.id if user else None
    await session.flush()
    await message.reply(f"✅ {title} привязан к этому чату\nID: {message.chat.id}")
