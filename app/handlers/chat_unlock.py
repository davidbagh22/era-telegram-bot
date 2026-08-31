from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import Message

from app.config import Settings
from app.services.chat_permissions_service import restore_general_chat_member

router = Router(name="chat_unlock")


@router.message(Command("unlock_chat"), F.chat.type == "private")
async def unlock_general_chat(message: Message, bot: Bot, settings: Settings) -> None:
    """Emergency self-service repair for historical Telegram mutes."""
    if message.from_user is None:
        return
    repaired = await restore_general_chat_member(
        bot,
        settings,
        message.from_user.id,
    )
    if repaired:
        await message.answer(
            "✅ Старое ограничение в общем чате снято. Можно писать сразу."
        )
    else:
        await message.answer(
            "✅ Права в общем чате проверены. Если Telegram всё ещё показывает "
            "старое ограничение, закройте чат и откройте его снова."
        )
