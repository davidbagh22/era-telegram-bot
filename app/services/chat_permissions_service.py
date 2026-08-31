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


async def restore_general_chat_member(
    bot: Bot,
    settings: Settings,
    telegram_id: int,
) -> bool:
    """Repair a legacy per-user Telegram restriction in the general chat.

    Older versions of ERA could apply a personal `restrictChatMember` mute to
    people who had not completed registration yet. Changing the chat's default
    permissions does not remove that stored per-user override, and Telegram's
    Bot API cannot enumerate every historical member. This helper therefore
    repairs the exact person whenever we learn their Telegram id from a private
    interaction with the bot.

    Deliberately only touches `restricted` members. It never unbans kicked or
    banned users, so explicit moderation/admin decisions are not reversed.
    """
    chat_id = settings.general_chat_id
    if not chat_id:
        return False

    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=telegram_id)
        raw_status = getattr(member, "status", "")
        status = str(getattr(raw_status, "value", raw_status)).casefold()
        if status != "restricted":
            return False
        await bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=telegram_id,
            permissions=writable_permissions(),
        )
        logger.info(
            "Restored legacy general-chat write permissions telegram_id=%s chat=%s",
            telegram_id,
            chat_id,
        )
        return True
    except TelegramAPIError:
        logger.warning(
            "Could not inspect/restore general-chat permissions telegram_id=%s chat=%s",
            telegram_id,
            chat_id,
            exc_info=True,
        )
        return False


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
