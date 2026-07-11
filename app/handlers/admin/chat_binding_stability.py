from __future__ import annotations

from typing import Any

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import AppSetting, ChatGreeting, User
from app.states.admin import AdminSettingsStates
from app.utils import texts
from app.utils.constants import Role

router = Router(name="admin_chat_binding_stability")

CHAT_BINDINGS = {
    "era_channel": ("era_channel_id", None, "Канал ЭРА"),
    "general": ("general_chat_id", "general", "Общий чат"),
    "internal": ("internal_department_chat_id", "internal", "Внутренние связи"),
    "external": ("external_department_chat_id", "external", "Внешние связи"),
    "leaders": ("leaders_chat_id", "leaders", "Чат лидеров"),
}


def _active_permissions(user: User | None) -> set[str]:
    return {
        grant.permission
        for grant in (getattr(user, "permission_grants", None) or [])
        if grant.is_active
    }


def _can_bind(user: User | None, settings: Settings, telegram_id: int) -> bool:
    if telegram_id in settings.admin_ids:
        return True
    if not user or user.is_blocked or user.is_archived:
        return False
    if user.role == Role.ADMIN:
        return True
    return "people.manage" in _active_permissions(user)


async def _guard(message: Message, user: User | None, settings: Settings) -> bool:
    if not message.from_user or not _can_bind(user, settings, message.from_user.id):
        await message.answer(texts.NO_ACCESS)
        return False
    return True


def _forwarded_chat(message: Message) -> Any | None:
    origin = message.forward_origin
    for attr in ("chat", "sender_chat"):
        chat = getattr(origin, attr, None)
        if chat is not None:
            return chat
    return getattr(message, "forward_from_chat", None)


async def _save_binding(
    *,
    session: AsyncSession,
    settings: Settings,
    user: User | None,
    setting_key: str,
    greeting_key: str | None,
    chat_id: int,
) -> None:
    setattr(settings, setting_key, chat_id)
    current = await session.scalar(select(AppSetting).where(AppSetting.key == setting_key))
    if current:
        current.value = str(chat_id)
        current.updated_by = user.id if user else None
    else:
        session.add(
            AppSetting(
                key=setting_key,
                value=str(chat_id),
                updated_by=user.id if user else None,
            )
        )
    if greeting_key:
        greeting = await session.scalar(
            select(ChatGreeting).where(ChatGreeting.chat_key == greeting_key)
        )
        if greeting:
            greeting.chat_id = chat_id
            greeting.updated_by = user.id if user else None
    await session.flush()


@router.message(AdminSettingsStates.chat_bind)
async def bind_chat_finish_stable(
    message: Message,
    user: User | None,
    settings: Settings,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _guard(message, user, settings):
        return
    data = await state.get_data()
    key = data.get("bind_chat_key")
    binding = CHAT_BINDINGS.get(str(key))
    if binding is None:
        await state.clear()
        await message.answer("Не понял, какой чат нужно подключить. Откройте настройки и выберите чат заново")
        return

    chat = _forwarded_chat(message)
    if chat is None:
        await message.answer(
            "Telegram не передал ID чата в пересланном сообщении\n\n"
            "Самый надёжный способ: добавьте бота администратором в нужный чат или канал и напишите прямо там одну из команд:\n"
            "/bind general — общий чат\n"
            "/bind internal — внутренние связи\n"
            "/bind external — внешние связи\n"
            "/bind leaders — чат лидеров\n"
            "/bind channel — канал ЭРА\n\n"
            "Если хотите продолжить через пересылку, перешлите сообщение именно из канала/чата, а не сообщение от участника"
        )
        return

    setting_key, greeting_key, title = binding
    await _save_binding(
        session=session,
        settings=settings,
        user=user,
        setting_key=setting_key,
        greeting_key=greeting_key,
        chat_id=chat.id,
    )
    await state.clear()
    await message.answer(
        f"Готово — {title} подключён к боту\nID: {chat.id}\n\nНастройка уже применяется без перезапуска"
    )
