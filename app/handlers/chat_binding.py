from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
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
    "media": ("media_chat_id", "media", "Медиа"),
    "channel": ("era_channel_id", "era_channel", "Канал ЭРА"),
    "era_channel": ("era_channel_id", "era_channel", "Канал ЭРА"),
}


def _can_bind(user: User | None, settings: Settings, telegram_id: int) -> bool:
    return bool(
        telegram_id in settings.admin_ids
        or (user and user.role == Role.ADMIN and not user.is_blocked and not user.is_archived)
    )


def _binding_conflict(key: str, chat_id: int, settings: Settings) -> str | None:
    """Never reuse the general chat as the Leaders workcenter, or vice versa."""
    if key == "leaders" and chat_id == settings.general_chat_id:
        return "Это общий чат ЭРА. Чат лидеров должен быть отдельным."
    if key == "general" and chat_id == settings.leaders_chat_id:
        return "Это чат лидеров. Нельзя назначить его общим чатом ЭРА."
    return None


def _leaders_permission_error(chat, member) -> str | None:
    """Read-only Telegram preflight before persisting a Leaders chat binding."""
    if chat.type not in {"group", "supergroup"}:
        return "Чат лидеров должен быть группой или супергруппой Telegram."
    if member.status not in {"administrator", "creator"}:
        return "Сделайте бота администратором чата лидеров и повторите /bind leaders."
    if chat.is_forum and not getattr(member, "can_manage_topics", False):
        return "Для форума лидеров дайте боту право управлять темами и повторите /bind leaders."
    return None


@router.message(Command("bind"), ~F.chat.type.in_({"private"}))
async def bind_current_chat(
    message: Message,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if not message.from_user or not _can_bind(user, settings, message.from_user.id):
        await message.reply("Привязать чат может только администратор ЭРА")
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or parts[1].strip().lower() not in CHAT_KEYS:
        await message.reply(
            "Напишите так: /bind general\n\n"
            "Варианты: general, internal, external, leaders, media, channel"
        )
        return

    raw_key = parts[1].strip().lower()
    setting_key, greeting_key, title = CHAT_KEYS[raw_key]

    conflict = _binding_conflict(raw_key, message.chat.id, settings)
    if conflict:
        await message.reply(conflict)
        return
    if raw_key == "leaders":
        try:
            chat = await bot.get_chat(message.chat.id)
            member = await bot.get_chat_member(message.chat.id, bot.id)
        except TelegramAPIError:
            await message.reply("Не удалось проверить права бота в чате лидеров. Повторите привязку позже.")
            return
        permission_error = _leaders_permission_error(chat, member)
        if permission_error:
            await message.reply(permission_error)
            return

    stored = await session.scalar(select(AppSetting).where(AppSetting.key == setting_key))
    if stored is None:
        stored = AppSetting(
            key=setting_key,
            value=str(message.chat.id),
            updated_by=user.id if user else None,
        )
        session.add(stored)
    else:
        stored.value = str(message.chat.id)
        stored.updated_by = user.id if user else None

    greeting = await session.scalar(
        select(ChatGreeting).where(ChatGreeting.chat_key == greeting_key)
    )
    if greeting is not None:
        greeting.chat_id = message.chat.id
        greeting.updated_by = user.id if user else None

    await session.commit()
    setattr(settings, setting_key, message.chat.id)
    await message.reply(
        f"✅ {title} привязан. Настройка сохранена в ЭРА и применяется без перезапуска."
    )
