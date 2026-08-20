from __future__ import annotations

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from sqlalchemy import select

from app.config import Settings
from app.database.models import AuditLog
from app.keyboards.faq import general_chat_navigation_keyboard
from app.services.audit_service import audit

NAVIGATION_INSTALL_ACTION = "chat.quick_navigation_installed.v2"


async def ensure_general_chat_navigation(
    bot: Bot,
    settings: Settings,
    session_factory,
) -> None:
    """Install the persistent two-button dock once for the current general chat.

    Reply keyboards are attached to a normal Telegram message, so the bot must
    send one message after this feature is deployed. The audit marker makes the
    operation durable across restarts and prevents a stream of setup messages.
    """
    chat_id = settings.general_chat_id
    if not chat_id:
        return

    async with session_factory() as session:
        already_installed = await session.scalar(
            select(AuditLog.id)
            .where(
                AuditLog.action == NAVIGATION_INSTALL_ACTION,
                AuditLog.entity_type == "chat",
                AuditLog.entity_id == int(chat_id),
            )
            .limit(1)
        )
        if already_installed:
            return

        try:
            sent = await bot.send_message(
                int(chat_id),
                "⚡ Быстрый доступ ЭРА\n\n"
                "📅 События — актуальная афиша прямо в боте.\n"
                "🔥 Моя ЭРА — ваш личный профиль и путь в приложении.\n\n"
                "Кнопки теперь всегда доступны внизу чата.",
                reply_markup=general_chat_navigation_keyboard(),
                disable_notification=True,
            )
        except TelegramAPIError:
            await session.rollback()
            return

        await audit(
            session,
            actor_id=None,
            action=NAVIGATION_INSTALL_ACTION,
            entity_type="chat",
            entity_id=int(chat_id),
            new_value={"message_id": sent.message_id, "version": 2},
        )
        await session.commit()
