from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import ChatPermissions
from sqlalchemy import select

from app.config import Settings
from app.database.models import User

logger = logging.getLogger(__name__)


def writable_permissions() -> ChatPermissions:
    return ChatPermissions(
        can_send_messages=True,
        can_send_audios=True,
        can_send_documents=True,
        can_send_photos=True,
        can_send_videos=True,
        can_send_video_notes=True,
        can_send_voice_notes=True,
        can_send_polls=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True,
    )


async def enforce_general_chat_writable(bot: Bot, settings: Settings, session_factory) -> tuple[int, int]:
    """Only restore Telegram write permissions. Never send/edit/pin a message."""
    chat_id = settings.general_chat_id
    if not chat_id:
        return 0, 0

    fixed = failed = 0
    try:
        await bot.set_chat_permissions(chat_id=chat_id, permissions=writable_permissions())
        fixed += 1
    except TelegramAPIError:
        logger.exception("Could not set default writable permissions chat=%s", chat_id)
        failed += 1

    async with session_factory() as session:
        telegram_ids = list((await session.scalars(select(User.telegram_id))).all())

    for telegram_id in telegram_ids:
        try:
            member = await bot.get_chat_member(chat_id=chat_id, user_id=telegram_id)
            raw_status = getattr(member, "status", "")
            status = str(getattr(raw_status, "value", raw_status)).casefold()
            if status not in {"member", "administrator", "creator", "restricted"}:
                continue
            if status == "restricted":
                await bot.restrict_chat_member(
                    chat_id=chat_id,
                    user_id=telegram_id,
                    permissions=writable_permissions(),
                )
                fixed += 1
        except TelegramAPIError:
            continue
    return fixed, failed
