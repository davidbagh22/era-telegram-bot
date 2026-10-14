from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router(name="chat_unlock")


@router.message(Command("unlock_chat"), F.chat.type == "private")
async def unlock_general_chat(message: Message) -> None:
    """Explain that Telegram moderators manage member-level restrictions."""
    await message.answer(
        "Права участников в общем чате меняют только модераторы. "
        "Напишите модератору, если считаете, что ограничение выставлено ошибочно."
    )
